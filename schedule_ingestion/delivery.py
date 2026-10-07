"""Durable delivery state; ambiguous sends require explicit operator resolution."""
from copy import deepcopy
import uuid

from django.db import transaction
from django.conf import settings
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from urllib.parse import urlsplit

from .models import Publication, PublicationDelivery
from .run_storage import load_export


class DeliveryUncertain(ValueError):
    pass


def pipeline_summary(publication):
    from scheduler.dtos import PipelineSummary
    revision = publication.revision
    payload = load_export(revision.pk)
    summary = PipelineSummary(sync_summary=publication.summary or {'added': [], 'updated': [], 'removed': []},
        spider_result=dict(total_groups=len(payload['groups']), parsed=len(payload['groups']),
            skipped=0, no_change=0, errors=0, total_lessons=len(payload['lessons']),
            closing_reason='tableparser_' + publication.status),
        publication=dict(id=str(publication.pk), run_id=str(revision.run_id),
            revision_id=str(revision.pk), revision_number=revision.number, status=publication.status,
            start=publication.start_date.isoformat(), end=publication.end_date.isoformat() if publication.end_date else None,
            needs_review_count=sum(row.get('review_status') == 'needs_review' for row in payload['lessons'])))
    base_url = getattr(settings, 'TABLEPARSER_PUBLIC_BASE_URL', '').rstrip('/')
    if base_url:
        parsed = urlsplit(base_url)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError('Invalid public application URL')
        try:
            path = reverse('admin:schedule_ingestion_publication_change', args=[publication.pk])
        except NoReverseMatch:
            pass  # Minimal test/worker URLconfs may not expose the admin.
        else:
            summary.publication['url'] = base_url + path
    return summary.model_dump()


def deliver_publication(publication_id, phase):
    if phase not in ('notifications', 'report'):
        raise ValueError('Unknown delivery phase')
    with transaction.atomic():
        publication = Publication.objects.select_for_update().select_related('revision').get(pk=publication_id)
        if publication.status not in ('applied', 'superseded'):
            raise ValueError('Publication has not been applied')
        delivery = PublicationDelivery.objects.get(publication=publication, phase=phase)
        if delivery.status in ('completed', 'skipped'):
            return deepcopy(delivery.result)
        if delivery.status != 'pending':
            raise DeliveryUncertain('Delivery is running or uncertain; automatic resend is disabled')
        summary = pipeline_summary(publication)
        if phase == 'report':
            notices = PublicationDelivery.objects.get(publication=publication, phase='notifications')
            if notices.status not in ('completed', 'skipped'):
                raise DeliveryUncertain('Notification delivery has not completed')
            if notices.status == 'completed':
                summary = deepcopy(notices.result)
        token = uuid.uuid4()
        delivery.status, delivery.token, delivery.started_at = 'sending', token, timezone.now()
        delivery.save(update_fields=['status', 'token', 'started_at'])
    try:
        from scheduler.tasks.notification import send_lessons_refresh_notifications, deliver_admin_report
        if phase == 'notifications':
            result = send_lessons_refresh_notifications.run(summary)
        else:
            _, result = deliver_admin_report(summary)
        updated = PublicationDelivery.objects.filter(pk=delivery.pk, token=token, status='sending').update(
            status='completed', finished_at=timezone.now(), result=result)
        if not updated:
            raise DeliveryUncertain('Delivery state changed during sending')
        return result
    except Exception as error:
        PublicationDelivery.objects.filter(pk=delivery.pk, token=token, status='sending').update(
            status='uncertain', finished_at=timezone.now(), error_type=type(error).__name__[:200])
        raise
