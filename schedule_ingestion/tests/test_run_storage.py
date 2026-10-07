from datetime import date
import uuid
from unittest.mock import patch
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from schedule_ingestion.models import (ScheduleSource, SheetContent, ParseRun, RunSheet,
                                       ExportRevision, Observation, Confirmation)
from schedule_ingestion.run_storage import record_inputs, load_tables, save_export, load_export, StaleRevision


class RunStorageTests(TestCase):
    def setUp(self):
        self.source = ScheduleSource.objects.create(name='Расписание', spreadsheet_id='sheet-id',
                                                    sheet_names=['Первый', 'Второй'])
        self.sheets = {'Первый': [['Группа', 'А']], 'Второй': []}

    def record(self, **kwargs):
        params = dict(source_id=self.source.pk, sheets=self.sheets, captured_at=timezone.now(),
                      reference_date=date(2026, 12, 31), knowledge_as_of=timezone.now(),
                      parser_manifest={'wheel_sha256': 'a' * 64, 'resources': 'test'})
        params.update(kwargs)
        return record_inputs(**params)

    def export(self, run, **kwargs):
        params = dict(run_id=run.pk, expected_revision=0, request_id=uuid.uuid4(),
                      groups=['А', 'Б'], lessons=[{'group': 'А', 'subject': 'Физика', 'status': 'needs_review'}],
                      review_items=[{'id': 'review-1', 'status': 'needs_review'}], author='parser')
        params.update(kwargs)
        return save_export(**params)

    def test_deduplication_retains_every_sheet_and_original_configuration(self):
        first, second = self.record(), self.record()
        self.assertEqual(SheetContent.objects.count(), 2)
        self.assertEqual(RunSheet.objects.count(), 4)
        self.source.sheet_names = ['Другой']
        self.source.save()
        tables = load_tables(first.pk)
        self.assertEqual([t.name for t in tables], ['Первый', 'Второй'])
        self.assertEqual(tables[1].rows, [])
        self.assertEqual(tables[0].reference_date, date(2026, 12, 31))
        self.assertEqual([t.rows for t in load_tables(second.pk)], [t.rows for t in tables])

    def test_missing_failed_or_extra_sheet_is_not_a_successful_empty_response(self):
        for sheets in ({'Первый': []}, {'Первый': [], 'Второй': None},
                       {'Первый': [], 'Второй': [], 'Лишний': []}):
            with self.assertRaises(ValueError):
                self.record(sheets=sheets)
        self.assertEqual(ParseRun.objects.count(), 0)
        self.assertEqual(SheetContent.objects.count(), 0)
        self.assertEqual(len(load_tables(self.record(sheets={'Первый': [], 'Второй': []}).pk)), 2)

    def test_failed_write_rolls_back_run_and_contents(self):
        with patch.object(RunSheet, 'save', side_effect=RuntimeError('fail')):
            with self.assertRaises(RuntimeError):
                self.record()
        self.assertFalse(ParseRun.objects.exists())
        self.assertFalse(SheetContent.objects.exists())

    def test_review_creates_whole_version_and_does_not_learn_or_publish(self):
        run = self.record()
        old = self.export(run)
        updated = self.export(run, expected_revision=1, lessons=[{'group': 'Б', 'subject': 'Математика'}],
                              review_items=[], author='admin', reason='Исправлено после ревью')
        self.assertEqual(load_export(old.pk)['lessons'][0]['status'], 'needs_review')
        self.assertEqual(load_export(updated.pk)['lessons'], [{'group': 'Б', 'subject': 'Математика'}])
        self.assertEqual(load_export(updated.pk)['groups'], ['А', 'Б'])
        self.assertEqual(updated.number, 2)
        self.assertFalse(Observation.objects.exists())
        self.assertFalse(Confirmation.objects.exists())
        with self.assertRaises(ValueError):
            old.save()

    def test_stale_editor_and_retry_identity(self):
        run, key = self.record(), uuid.uuid4()
        first = self.export(run, request_id=key)
        self.export(run, expected_revision=1)
        self.assertEqual(self.export(run, request_id=key).pk, first.pk)
        with self.assertRaises(StaleRevision):
            self.export(run)
        with self.assertRaisesRegex(ValueError, 'different edit'):
            self.export(run, request_id=key, author='someone-else')
        self.assertEqual(ExportRevision.objects.count(), 2)

    def test_empty_group_schedule_retained_and_unknown_group_rejected(self):
        run = self.record()
        version = self.export(run, lessons=[], review_items=[])
        self.assertEqual(load_export(version.pk)['groups'], ['А', 'Б'])
        with self.assertRaises(ValueError):
            self.export(run, expected_revision=1, lessons=[{'group': 'В'}])

    def test_tampered_content_is_rejected(self):
        run = self.record()
        version = self.export(run)
        ExportRevision.objects.filter(pk=version.pk).update(payload='{}')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            load_export(version.pk)
        SheetContent.objects.all().update(payload='[]')
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            load_tables(run.pk)


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row-lock test')
class ConcurrentExportTests(TransactionTestCase):
    def test_concurrent_editors_and_duplicate_requests(self):
        source = ScheduleSource.objects.create(name='Test', spreadsheet_id='id', sheet_names=['Sheet'])
        for retry in (False, True):
            run = record_inputs(source_id=source.pk, sheets={'Sheet': []},
                captured_at=timezone.now(), reference_date=date(2026, 10, 7),
                knowledge_as_of=timezone.now(), parser_manifest={'release': 'test'})
            barrier = Barrier(2)
            keys = [uuid.uuid4(), uuid.uuid4()]
            if retry:
                keys[1] = keys[0]
            def edit(key):
                try:
                    barrier.wait(timeout=10)
                    return save_export(run_id=run.pk, expected_revision=0, request_id=key,
                        groups=['А'], lessons=[], review_items=[], author='admin').pk
                except StaleRevision:
                    return 'stale'
                finally:
                    connections.close_all()
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(edit, keys))
            self.assertEqual(run.exports.count(), 1)
            if retry:
                self.assertEqual(results[0], results[1])
                self.assertNotIn('stale', results)
            else:
                self.assertEqual(results.count('stale'), 1)
