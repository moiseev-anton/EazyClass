"""Prepare and apply one explicit export; notification delivery is a separate stage."""
from datetime import date
import json
import re
import uuid

from django.db import transaction
from django.utils import timezone

from scheduler.dtos.lesson_sync_range import LessonSyncRange
from scheduler.fetched_data_sync.lessons.lessons_sync_manager import LessonsSyncManager, ScrapyFetchResult
from scheduler.models import Group, Teacher
from scheduler.schedule_write_guard import schedule_write_guard
from .models import ExportRevision, Publication, ScheduleWriteEvent, PublicationDelivery
from .run_storage import load_export, encode, digest


def group_key(value):
    return re.sub(r'[^а-яА-ЯёЁa-zA-Z0-9]', '', value).lower()


def integer(value, *, minimum=0, maximum=None):
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r'\d+', value):
        number = int(value)
    else:
        raise ValueError('Expected a schedule integer')
    if number < minimum or (maximum is not None and number > maximum):
        raise ValueError('Schedule integer is out of range')
    return number


def optional_text(value):
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('Expected schedule text')
    return value.strip() or None


def prepare_payload(export):
    groups_by_name = {}
    for group in Group.objects.filter(is_active=True).values('id', 'title'):
        groups_by_name.setdefault(group_key(group['title']), []).append(group['id'])
    groups = {}
    for name in export['groups']:
        matches = groups_by_name.get(group_key(name), [])
        if len(matches) != 1:
            raise ValueError('Unknown or ambiguous group: ' + name)
        groups[name] = matches[0]
    teacher_names = {}
    for teacher in Teacher.objects.values('short_name', 'full_name'):
        teacher_names.setdefault(teacher['short_name'], set()).add(teacher['full_name'])
    items = []
    for row in export['lessons']:
        if row.get('group') not in groups:
            raise ValueError('Lesson is outside declared groups')
        day = date.fromisoformat(row['date']).isoformat()
        teacher = optional_text(row.get('teacher'))
        matches = teacher_names.get(teacher, set())
        # Ambiguity preserves the parsed text, never picks an arbitrary person.
        if len(matches) == 1:
            teacher = next(iter(matches))
        if 'annotations' in row:
            from schedule_csv import annotation_text
            notes = row['annotations']
            if not isinstance(notes, list) or any(not isinstance(n, dict) or
                    not isinstance(n.get('text', ''), str) for n in notes):
                raise ValueError('Invalid structured annotations')
            annotation = annotation_text(notes)
        else:
            annotation = optional_text(row.get('annotation'))
        items.append(dict(group_id=groups[row['group']],
            period=dict(date=day, lesson_number=integer(row['lesson_number'], minimum=1),
                        part=integer(row.get('part') if row.get('part') not in (None, '') else 0, maximum=2)),
            subgroup=integer(row.get('subgroup') if row.get('subgroup') not in (None, '') else 0, maximum=9),
            teacher={'full_name': teacher}, subject={'title': optional_text(row.get('subject'))},
            classroom={'title': optional_text(row.get('classroom'))}, annotation={'title': annotation}))
    return dict(groups={str(pk): '' for pk in groups.values()}, lessons=items)


def prepare_publication(revision_id, *, requested_by, automatic=False,
                        start_day_offset=0, end_day_offset=None, request_id=None, resolved_range=None):
    if type(automatic) is not bool or not isinstance(requested_by, str) or not requested_by.strip():
        raise ValueError('Explicit publication mode and requester are required')
    key = uuid.UUID(str(request_id)) if request_id else uuid.uuid4()
    if resolved_range is not None:
        if type(start_day_offset) is not int or start_day_offset != 0 or end_day_offset is not None:
            raise ValueError('Resolved range cannot be combined with offsets')
        bounds = LessonSyncRange.from_dict(resolved_range)
    else:
        bounds = LessonSyncRange.from_offsets(start_day_offset=start_day_offset, end_day_offset=end_day_offset)
    # A repeated preparation must use the already fixed range, even after midnight.
    with transaction.atomic():
        revision = ExportRevision.objects.select_for_update().get(pk=revision_id)
        old = Publication.objects.filter(pk=key).first()
        if old:
            if (old.revision_id, old.automatic, old.requested_by) != (revision.pk, automatic, requested_by):
                raise ValueError('Publication request ID was already used')
            if json.loads(old.prepared_payload)['offsets'] != [start_day_offset, end_day_offset]:
                raise ValueError('Publication request offsets changed')
            if resolved_range is not None and (old.start_date, old.end_date) != (bounds.start, bounds.end):
                raise ValueError('Publication request range changed')
            return old
        prepared = prepare_payload(load_export(revision.pk))
        prepared['offsets'] = [start_day_offset, end_day_offset]
        payload = encode(prepared)
        return Publication.objects.create(id=key, revision=revision, requested_by=requested_by,
            automatic=automatic, start_date=bounds.start, end_date=bounds.end,
            prepared_payload=payload, prepared_sha256=digest(payload))


def apply_publication(publication_id):
    # The outer transaction keeps schedule, change summary and status atomic.
    with schedule_write_guard():
        publication = Publication.objects.select_for_update().select_related('revision__run').get(pk=publication_id)
        if publication.status != 'pending':
            ensure_deliveries(publication)
            return publication
        if digest(publication.prepared_payload) != publication.prepared_sha256:
            raise ValueError('Prepared publication hash mismatch')
        payload = json.loads(publication.prepared_payload)
        bounds = LessonSyncRange(publication.start_date, publication.end_date)
        group_ids = set(payload['groups'])
        if set(map(str, Group.objects.filter(pk__in=group_ids).values_list('pk', flat=True))) != group_ids:
            raise ValueError('A prepared group no longer exists')
        if publication.automatic:
            events = ScheduleWriteEvent.objects.filter(observed_at__gt=publication.revision.run.captured_at)
            if bounds.end:
                events = events.filter(start_date__lte=bounds.end)
            for event in events:
                if (event.end_date is None or event.end_date >= bounds.start) and group_ids.intersection(event.group_ids):
                    publication.status = 'superseded'
                    publication.save(update_fields=['status'])
                    ensure_deliveries(publication)
                    return publication
        manager = LessonsSyncManager(start_sync_day=bounds.start, end_sync_day=bounds.end, use_redis=False)
        publication.summary = manager.update_from_data(
            ScrapyFetchResult(payload['groups'], payload['lessons'], set()),
            observed_at=publication.revision.run.captured_at if publication.automatic else timezone.now())
        publication.status = 'applied'
        publication.applied_at = timezone.now()
        publication.save(update_fields=['summary', 'status', 'applied_at'])
        ensure_deliveries(publication)
        return publication


def ensure_deliveries(publication):
    for phase in ('notifications', 'report'):
        PublicationDelivery.objects.get_or_create(publication=publication, phase=phase, defaults={
            'status': 'skipped' if phase == 'notifications' and publication.status == 'superseded' else 'pending'})
