from datetime import date
from pathlib import Path
import tempfile
import os
import uuid
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from schedule_ingestion.models import ScheduleSource, ParseAttempt, ExportRevision, Observation, Confirmation
from schedule_ingestion.parser_runtime import runtime_manifest
from schedule_ingestion.parse_execution import execute_parse, abandon_attempt, ParseBusy, AttemptAbandoned
from schedule_ingestion.run_storage import record_inputs, load_export, save_export


@skipUnless(apps.is_installed('scheduler'), 'Requires catalog_settings')
class ParseExecutionTests(TransactionTestCase):
    def setUp(self):
        from scheduler.models import Teacher, Classroom
        Teacher.objects.create(full_name='Иванов Иван Иванович', short_name='Иванов И.И.', is_active=False)
        Classroom.objects.create(title='100', is_active=False)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'config').mkdir()
        for name in ('extraction_proposals.json', 'subject_proposals.json'):
            (self.root / 'config' / name).write_text('{"enabled":false}', encoding='utf-8')
        self.source = ScheduleSource.objects.create(name='Test', spreadsheet_id='sheet-id', sheet_names=['Sheet'])
        self.catalog_source = 'https://example.invalid/api/v1'
        self.manifest = runtime_manifest(self.root, catalog_source=self.catalog_source)
        self.run = record_inputs(source_id=self.source.pk,
            sheets={'Sheet': [[], ['', '', 'А'], ['07.10.2026', '1', 'Физика']]},
            captured_at=timezone.now(), reference_date=date(2026, 10, 7),
            knowledge_as_of=timezone.now(), parser_manifest=self.manifest)

    def execute(self):
        return execute_parse(self.run.pk, resource_root=self.root, catalog_source=self.catalog_source)

    def test_real_installed_parser_uses_live_catalogs_and_db_memory(self):
        with patch('sqlite3.connect', side_effect=AssertionError('Parser must not open SQLite')):
            export = self.execute()
        payload = load_export(export.pk)
        self.assertEqual(payload['groups'], ['А'])
        self.assertEqual(len(payload['lessons']), 1)
        self.assertEqual(payload['lessons'][0]['review_status'], 'needs_review')
        self.assertTrue(payload['review_items'])
        self.assertEqual(ParseAttempt.objects.get().status, 'succeeded')
        self.assertFalse(Observation.objects.exists())
        self.assertFalse(Confirmation.objects.exists())
        # A delivery retry must return the parser's version, not the reviewed head.
        corrected = save_export(run_id=self.run.pk, expected_revision=1, request_id=uuid.uuid4(),
            groups=['А'], lessons=[], review_items=[], author='admin')
        with patch('eazyclass_tableparser.parse_tables', side_effect=AssertionError('Unexpected replay')):
            self.assertEqual(self.execute().pk, export.pk)
        self.assertEqual(load_export(corrected.pk)['lessons'], [])
        self.assertEqual(ParseAttempt.objects.count(), 1)

    def test_error_creates_no_export_and_retry_can_succeed(self):
        with patch('eazyclass_tableparser.parse_tables', side_effect=RuntimeError('sensitive cell text')):
            with self.assertRaises(RuntimeError):
                self.execute()
        attempt = ParseAttempt.objects.get()
        self.assertEqual(attempt.status, 'failed')
        self.assertEqual(attempt.error_type, 'RuntimeError')
        self.assertFalse(ExportRevision.objects.exists())
        self.execute()
        self.assertEqual(ParseAttempt.objects.count(), 2)
        self.assertEqual(ExportRevision.objects.count(), 1)

    def test_busy_attempt_requires_explicit_recovery(self):
        attempt = ParseAttempt.objects.create(run=self.run)
        with self.assertRaises(ParseBusy):
            self.execute()
        self.assertTrue(abandon_attempt(attempt.pk))
        self.assertFalse(abandon_attempt(attempt.pk))
        self.execute()
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, 'abandoned')

    def test_abandoned_worker_cannot_save_late_result(self):
        from eazyclass_tableparser import parse_tables
        def parse(*args):
            result = parse_tables(*args)
            abandon_attempt(ParseAttempt.objects.get(status='running').pk)
            return result
        with patch('eazyclass_tableparser.parse_tables', side_effect=parse):
            with self.assertRaises(AttemptAbandoned):
                self.execute()
        self.assertFalse(ExportRevision.objects.exists())
        self.assertEqual(ParseAttempt.objects.get().status, 'abandoned')

    def test_runtime_drift_before_or_during_parse_is_rejected(self):
        from eazyclass_tableparser import parse_tables
        added = self.root / 'config' / 'new.json'
        added.write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'differ'):
            self.execute()
        added.unlink()
        def parse(*args):
            result = parse_tables(*args)
            added.write_text('{}', encoding='utf-8')
            return result
        with patch('eazyclass_tableparser.parse_tables', side_effect=parse):
            with self.assertRaisesRegex(ValueError, 'changed during'):
                self.execute()
        self.assertFalse(ExportRevision.objects.exists())

    def test_export_and_success_status_commit_together(self):
        original = ParseAttempt.save
        def fail(instance, *args, **kwargs):
            if instance.status == 'succeeded':
                raise RuntimeError('Failed to save attempt')
            return original(instance, *args, **kwargs)
        with patch.object(ParseAttempt, 'save', fail):
            with self.assertRaises(RuntimeError):
                self.execute()
        self.assertFalse(ExportRevision.objects.exists())
        self.run.refresh_from_db()
        self.assertEqual(self.run.head_revision, 0)
        self.assertEqual(ParseAttempt.objects.get().status, 'failed')

    @skipUnless(os.environ.get('TABLEPARSER_TEST_RESOURCE_ROOT'), 'Opt-in trained resource integration')
    def test_existing_trained_resource_bundle(self):
        root = Path(os.environ['TABLEPARSER_TEST_RESOURCE_ROOT'])
        manifest = runtime_manifest(root, catalog_source=self.catalog_source)
        run = record_inputs(source_id=self.source.pk,
            sheets={'Sheet': [[], ['', '', 'А'], ['07.10.2026', '1', 'Физика Иванов И.И. (100)']]},
            captured_at=timezone.now(), reference_date=date(2026, 10, 7),
            knowledge_as_of=timezone.now(), parser_manifest=manifest)
        with patch('sqlite3.connect', side_effect=AssertionError('No SQLite knowledge access')):
            result = execute_parse(run.pk, resource_root=root, catalog_source=self.catalog_source)
        self.assertEqual(len(load_export(result.pk)['lessons']), 1)
        self.assertEqual(runtime_manifest(root, catalog_source=self.catalog_source), manifest)

    def test_full_eager_chain_with_only_network_replaced(self):
        from schedule_ingestion.tasks import source_parse_chain
        self.source.sheet_gids = {'Sheet': 0}
        self.source.save()
        with override_settings(TABLEPARSER_RUNTIME={
                'resource_root': str(self.root), 'catalog_source': self.catalog_source}):
            with patch('schedule_ingestion.acquisition.fetch_sheet',
                       return_value=[[], ['', '', 'А'], ['07.10.2026', '1', 'Физика']]):
                export_id = source_parse_chain(self.source.pk).apply(throw=True).get()
        self.assertEqual(len(load_export(export_id)['lessons']), 1)
        self.assertEqual(ParseAttempt.objects.get().status, 'succeeded')
