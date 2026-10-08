"""Explicit, audited resolution of an ambiguous external side effect."""
import uuid

from django.db import transaction
from django.utils import timezone

from .models import Publication, PublicationDelivery, DeliveryResolution


def resolve_delivery(publication_id, phase, *, request_id, expected_token, decision,
                     actor, reason, worker_stopped=False):
    if phase not in ('notifications', 'report') or decision not in ('retry', 'skip'):
        raise ValueError('Unknown phase or recovery decision')
    if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
        raise ValueError('Actor and reason are required')
    request_id, expected_token = uuid.UUID(str(request_id)), uuid.UUID(str(expected_token))
    with transaction.atomic():
        publication = Publication.objects.select_for_update().get(pk=publication_id)
        delivery = PublicationDelivery.objects.select_for_update().get(publication=publication, phase=phase)
        existing = DeliveryResolution.objects.filter(pk=request_id).first()
        if existing:
            if (existing.delivery_id != delivery.pk or existing.decision != decision
                    or existing.actor != actor or existing.reason != reason
                    or existing.worker_stopped != worker_stopped
                    or existing.previous['token'] != str(expected_token)):
                raise ValueError('Recovery request ID already has different parameters')
            return existing
        if delivery.status not in ('sending', 'uncertain') or delivery.token != expected_token:
            raise ValueError('Delivery state changed; inspect it again before resolving')
        if delivery.status == 'sending' and not worker_stopped:
            raise ValueError('Confirm that the sending worker has stopped before resolving')
        previous = dict(status=delivery.status, token=str(delivery.token), result=delivery.result,
            error_type=delivery.error_type,
            started_at=delivery.started_at.isoformat() if delivery.started_at else None,
            finished_at=delivery.finished_at.isoformat() if delivery.finished_at else None)
        resolution = DeliveryResolution.objects.create(id=request_id, delivery=delivery,
            decision=decision, actor=actor, reason=reason, worker_stopped=worker_stopped, previous=previous)
        delivery.status = 'pending' if decision == 'retry' else 'skipped'
        delivery.token = None  # Fence completion from the abandoned attempt.
        delivery.started_at = None
        delivery.finished_at = timezone.now() if decision == 'skip' else None
        delivery.error_type = ''
        delivery.result = {}
        delivery.save(update_fields=['status', 'token', 'started_at', 'finished_at', 'error_type', 'result'])
        return resolution
