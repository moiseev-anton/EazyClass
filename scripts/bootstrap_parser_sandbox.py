"""Initialize only the dedicated local sandbox after restoring its DB copy."""
import os
import uuid

import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.utils import timezone

if not getattr(settings, 'TABLEPARSER_LOCAL_SANDBOX', False):
    raise RuntimeError('Use eazyclass.local_parser_settings, never production settings')
if settings.DATABASES['default']['NAME'] != 'tableparser_sandbox':
    raise RuntimeError('Unexpected database')

call_command('migrate', interactive=False)
call_command('import_tableparser_knowledge', '/release/seed/knowledge.sqlite3', apply=True)
User = get_user_model()
user, created = User.objects.get_or_create(username='parser-admin', defaults={'is_staff': True, 'is_superuser': True})
if created:
    user.set_password(os.environ['SANDBOX_ADMIN_PASSWORD'])
    user.save()

from scheduler.models import Group
from schedule_ingestion.models import ScheduleSource
from schedule_ingestion.parser_runtime import runtime_manifest
from schedule_ingestion.run_storage import record_inputs, load_export, save_export
from schedule_ingestion.parse_execution import execute_parse

group, _ = Group.objects.get_or_create(title='ТЕСТ-ПАРСЕР')
source, _ = ScheduleSource.objects.get_or_create(name='Демонстрация ревью (без Google)', defaults={
    'spreadsheet_id': 'local-demo', 'sheet_names': ['Пример'], 'sheet_gids': {'Пример': 0}, 'enabled': False})
if not source.parserun_set.exists():
    source.enabled = True
    source.save(update_fields=['enabled'])
    now = timezone.now()
    today = timezone.localdate(now)
    profile = settings.TABLEPARSER_RUNTIME
    run = record_inputs(source_id=source.pk,
        sheets={'Пример': [[], ['', '', group.title], [today.strftime('%d.%m.%Y'), '1', 'Физика']]},
        captured_at=now, reference_date=today, knowledge_as_of=now,
        parser_manifest=runtime_manifest(profile['resource_root'], catalog_source=profile['catalog_source']))
    source.enabled = False
    source.save(update_fields=['enabled'])
    revision = execute_parse(run.pk, resource_root=profile['resource_root'], catalog_source=profile['catalog_source'])
    payload = load_export(revision.pk)
    if not payload['lessons']:
        raise RuntimeError('Demo parser returned no lessons')
    # Keep the original parser version; the extra demo version makes the review
    # exercise available even when the known subject parsed without a warning.
    for lesson in payload['lessons']:
        lesson['review_status'] = 'needs_review'
    revision = save_export(run_id=run.pk, expected_revision=revision.number,
        request_id=uuid.uuid4(), author='local-sandbox',
        reason='Демонстрационная версия для ручного ревью', **payload)
    print('Demo review:', f'http://127.0.0.1:18080/admin/schedule_ingestion/exportrevision/{revision.pk}/review/')
print('Sandbox initialized; outgoing delivery is disabled.')
