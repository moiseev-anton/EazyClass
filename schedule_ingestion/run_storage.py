"""Persist complete inputs and whole export revisions, without publishing or learning."""
from datetime import date
import hashlib
import json
import uuid

from django.db import transaction
from django.utils import timezone

from .models import ScheduleSource, SheetContent, ParseRun, RunSheet, ExportRevision


class StaleRevision(ValueError):
    pass


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(payload):
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def record_inputs(*, source_id, sheets, captured_at, reference_date, knowledge_as_of,
                  parser_manifest, using='default'):
    """sheets maps EVERY configured sheet name to successfully fetched string rows.

    A missing/failed sheet must never be represented by an empty successful one.
    Empty lists explicitly represent successful empty responses. Call only after
    all fetches succeed; this function does not fetch or infer success.
    """
    if not isinstance(sheets, dict):
        raise ValueError('Expected a mapping of successful sheet responses')
    if type(reference_date) is not date:
        raise ValueError('reference_date must be a date')
    for instant in (captured_at, knowledge_as_of):
        if timezone.is_naive(instant):
            raise ValueError('Timestamps must include timezone')
    if not isinstance(parser_manifest, dict) or not parser_manifest:
        raise ValueError('Parser release/resource manifest is required')
    manifest = encode(parser_manifest)
    with transaction.atomic(using=using):
        source = ScheduleSource.objects.using(using).select_for_update().get(pk=source_id)
        names = source.sheet_names
        if (not isinstance(names, list) or not names or
                any(not isinstance(name, str) or not name.strip() or len(name) > 200 for name in names) or
                len(set(names)) != len(names)):
            raise ValueError('Invalid source sheet configuration')
        if not source.enabled:
            raise ValueError('Source is disabled')
        if set(sheets) != set(names):
            raise ValueError('All configured sheets are required, including unchanged sheets')
        payloads = []
        for name in names:
            rows = sheets[name]
            if not isinstance(rows, list) or any(not isinstance(row, list) or
                    any(not isinstance(cell, str) for cell in row) for row in rows):
                raise ValueError('Sheet rows must be lists of strings')
            payloads.append(encode(rows))
        run = ParseRun.objects.using(using).create(source=source,
            source_configuration=encode(dict(spreadsheet_id=source.spreadsheet_id, sheet_names=names)),
            captured_at=captured_at, reference_date=reference_date,
            knowledge_as_of=knowledge_as_of, parser_manifest=manifest)
        for position, (name, payload) in enumerate(zip(names, payloads)):
            content, _ = SheetContent.objects.using(using).get_or_create(
                sha256=digest(payload), defaults=dict(payload=payload))
            if content.payload != payload:
                raise ValueError('Stored sheet content hash mismatch')
            RunSheet.objects.using(using).create(run=run, name=name, position=position, content=content)
        return run


def load_tables(run_id, *, using='default'):
    from eazyclass_tableparser import RawTable
    run = ParseRun.objects.using(using).get(pk=run_id)
    rows = list(run.sheets.using(using).select_related('content').order_by('position'))
    if [row.name for row in rows] != json.loads(run.source_configuration)['sheet_names']:
        raise ValueError('Incomplete stored input')
    tables = []
    for row in rows:
        if digest(row.content.payload) != row.content_id:
            raise ValueError('Stored sheet content hash mismatch')
        tables.append(RawTable(row.name, json.loads(row.content.payload), run.reference_date))
    return tables


def save_export(*, run_id, expected_revision, request_id, groups, lessons, review_items,
                author, reason='', using='default'):
    """Append a whole version, with optimistic review locking and retry identity.

    needs_review is allowed and preserved. This service neither confirms knowledge
    nor dispatches synchronization; the caller must explicitly publish a version.
    """
    if type(expected_revision) is not int or expected_revision < 0:
        raise ValueError('Expected revision must be a non-negative integer')
    request_id = uuid.UUID(str(request_id))
    if not isinstance(author, str) or not author.strip() or not isinstance(reason, str):
        raise ValueError('Author and reason must be strings; author is required')
    if (not isinstance(groups, list) or any(not isinstance(g, str) or not g.strip() for g in groups)
            or len(set(groups)) != len(groups)):
        raise ValueError('Groups must be unique nonempty names')
    for items in (lessons, review_items):
        if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
            raise ValueError('Lessons and review items must be lists of objects')
    if any(lesson.get('group') not in groups for lesson in lessons):
        raise ValueError('Every lesson must belong to an explicitly supplied group')
    payload = encode(dict(groups=groups, lessons=lessons, review_items=review_items))
    sha = digest(payload)
    with transaction.atomic(using=using):
        run = ParseRun.objects.using(using).select_for_update().get(pk=run_id)
        previous = run.exports.using(using).filter(request_id=request_id).first()
        if previous:
            if (previous.payload, previous.author, previous.reason, previous.number) != (
                    payload, author, reason, expected_revision + 1):
                raise ValueError('Request ID was already used for a different edit')
            return previous
        if run.head_revision != expected_revision:
            raise StaleRevision('Export changed; reload before saving edits')
        revision = ExportRevision.objects.using(using).create(run=run,
            number=expected_revision + 1, request_id=request_id, author=author, reason=reason,
            payload=payload, sha256=sha)
        run.head_revision = revision.number
        run.save(using=using, update_fields=['head_revision'])
        return revision


def load_export(revision_id, *, using='default'):
    """Explicit version addressing; never silently substitute the latest export."""
    row = ExportRevision.objects.using(using).get(pk=revision_id)
    if digest(row.payload) != row.sha256:
        raise ValueError('Stored export hash mismatch')
    return json.loads(row.payload)
