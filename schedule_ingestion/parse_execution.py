"""Execute a saved run, without synchronization, notifications or learning."""
import json

from django.db import connections, transaction
from django.utils import timezone

from .models import ParseRun, ParseAttempt
from .run_storage import load_tables, save_export, load_export
from .parser_runtime import runtime_manifest
from .live_catalogs import load_live_catalogs
from .knowledge_reader import DjangoKnowledgeReader


class ParseBusy(ValueError):
    pass


class AttemptAbandoned(ValueError):
    pass


def abandon_attempt(attempt_id, *, using='default'):
    """Explicit operator recovery after worker loss; late completion is fenced out."""
    run_id = ParseAttempt.objects.using(using).get(pk=attempt_id).run_id
    with transaction.atomic(using=using):
        ParseRun.objects.using(using).select_for_update().get(pk=run_id)
        return ParseAttempt.objects.using(using).filter(pk=attempt_id, status='running').update(
            status='abandoned', finished_at=timezone.now()) == 1


def execute_parse(run_id, *, resource_root, catalog_source, using='default'):
    if connections[using].in_atomic_block or not connections[using].get_autocommit():
        raise ValueError('Execute parsing outside an existing transaction')
    with transaction.atomic(using=using):
        run = ParseRun.objects.using(using).select_for_update().get(pk=run_id)
        done = run.attempts.using(using).filter(status='succeeded').first()
        if done:
            load_export(done.export_id, using=using)
            return done.export
        if run.attempts.using(using).filter(status='running').exists():
            raise ParseBusy('This run is already being parsed')
        if run.head_revision:
            raise ValueError('Run already has an export; do not replace it with automatic parsing')
        attempt = ParseAttempt.objects.using(using).create(run=run)
    try:
        from eazyclass_tableparser import RuntimeResources, create_context, parse_tables
        expected = json.loads(run.parser_manifest)
        if runtime_manifest(resource_root, catalog_source=catalog_source) != expected:
            raise ValueError('Parser code, dependencies or resources differ from the saved manifest')
        tables = load_tables(run.pk, using=using)
        catalogs = load_live_catalogs(source=catalog_source, using=using)
        teachers, classrooms = catalogs.parser_services()
        ctx = create_context(knowledge=DjangoKnowledgeReader(using=using),
            resources=RuntimeResources.from_root(resource_root), as_of=run.knowledge_as_of,
            teacher_service=teachers, classroom_service=classrooms)
        result = parse_tables(tables, ctx)
        if runtime_manifest(resource_root, catalog_source=catalog_source) != expected:
            raise ValueError('Parser runtime changed during parsing')
        with transaction.atomic(using=using):
            ParseRun.objects.using(using).select_for_update().get(pk=run.pk)
            current = ParseAttempt.objects.using(using).get(pk=attempt.pk)
            if current.status != 'running':
                raise AttemptAbandoned('Attempt was abandoned; result will not be saved')
            export = save_export(run_id=run.pk, expected_revision=0, request_id=attempt.pk,
                groups=result.groups, lessons=result.lessons, review_items=result.review_items,
                author='parser', using=using)
            current.status = 'succeeded'
            current.finished_at = timezone.now()
            current.export = export
            current.save(using=using, update_fields=['status', 'finished_at', 'export'])
        return export
    except Exception as error:
        # Error messages may contain source cells or configuration secrets.
        ParseAttempt.objects.using(using).filter(pk=attempt.pk, status='running').update(
            status='failed', finished_at=timezone.now(), error_type=type(error).__name__[:200])
        raise
