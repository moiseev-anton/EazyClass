import uuid
from datetime import date
from unittest.mock import patch

from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from schedule_ingestion.models import ScheduleSource, Publication, ParseAttempt, ExportRevision
from schedule_ingestion.run_storage import record_inputs, save_export, load_tables
from schedule_ingestion.tasks import source_refresh_chain


class IncrementalRefreshTests(TestCase):
    def setUp(self):
        self.source = ScheduleSource.objects.create(name='Test', spreadsheet_id='book',
            sheet_names=['A', 'B'], sheet_gids={'A': 10, 'B': 20})
        self.rows = {'A': [['A data']], 'B': [['B data']]}
        self.bounds = {'start': '2026-10-10', 'end': None}
        self.manifest = {'release': 'test'}

    def capture(self, *, rows=None, bounds=None, force=False, manifest=None, day=None):
        now = timezone.now()
        return record_inputs(source_id=self.source.pk, sheets=rows or self.rows,
            captured_at=now, reference_date=day or date(2026, 10, 10), knowledge_as_of=now,
            parser_manifest=manifest or self.manifest, resolved_range=bounds or self.bounds,
            force=force, acquisition_id=uuid.uuid4())

    def publish(self, run, *, start=None, end=None, status='applied'):
        version = save_export(run_id=run.pk, expected_revision=0, request_id=uuid.uuid4(),
            groups=['A', 'B'], lessons=[], review_items=[], author='test')
        return Publication.objects.create(revision=version, requested_by='test',
            start_date=start or date(2026, 10, 10), end_date=end, status=status,
            applied_at=timezone.now() if status == 'applied' else None,
            prepared_payload='{}', prepared_sha256='unused')

    def selected(self, run):
        return list(run.sheets.filter(selected=True).order_by('position').values_list('name', flat=True))

    def test_initial_then_unchanged_has_complete_capture_but_no_parse_input(self):
        first = self.capture()
        self.assertEqual(self.selected(first), ['A', 'B'])
        self.publish(first)
        second = self.capture()
        self.assertEqual(second.sheets.count(), 2)
        self.assertEqual(self.selected(second), [])
        self.assertEqual(load_tables(second.pk), [])
        self.assertEqual(set(second.sheets.values_list('selection_reason', flat=True)), {'unchanged'})

    def test_changed_sheet_only_and_skipped_sheets_do_not_advance_publication(self):
        self.publish(self.capture())
        changed = {'A': [['new A']], 'B': self.rows['B']}
        partial = self.capture(rows=changed)
        self.assertEqual(self.selected(partial), ['A'])
        self.assertEqual([table.name for table in load_tables(partial.pk)], ['A'])
        self.publish(partial)
        self.assertEqual(self.selected(self.capture(rows=changed)), [])

    def test_fetch_parse_or_pending_and_superseded_publication_do_not_consume_content(self):
        for status in ['pending', 'superseded']:
            with self.subTest(status=status):
                self.publish(self.capture(), status=status)
                self.assertEqual(self.selected(self.capture()), ['A', 'B'])

    def test_partial_publication_does_not_extend_the_skipped_sheets_period(self):
        bounded = {'start': '2026-10-10', 'end': '2026-10-20'}
        self.publish(self.capture(bounds=bounded), end=date(2026, 10, 20))
        rows = {'A': [['new A']], 'B': self.rows['B']}
        partial = self.capture(rows=rows, bounds=bounded)
        self.assertEqual(self.selected(partial), ['A'])
        # An administrator publishes A over an unbounded range. B was not in its export.
        self.publish(partial)
        self.assertEqual(self.selected(self.capture(rows=rows)), ['B'])

    def test_rename_with_same_gid_requires_fresh_parser_sheet_names(self):
        self.publish(self.capture())
        self.source.sheet_names = ['Renamed', 'B']
        self.source.sheet_gids = {'Renamed': 10, 'B': 20}
        self.source.save()
        run = self.capture(rows={'Renamed': self.rows['A'], 'B': self.rows['B']})
        self.assertEqual(self.selected(run), ['Renamed'])
        self.assertEqual(run.sheets.get(name='Renamed').selection_reason, 'context')

    def test_reverting_to_an_older_hash_is_still_a_change(self):
        self.publish(self.capture())
        self.publish(self.capture(rows={'A': [['new A']], 'B': self.rows['B']}))
        self.assertEqual(self.selected(self.capture()), ['A'])

    def test_covered_actual_range_is_skipped_even_on_next_day(self):
        self.publish(self.capture())
        next_day = {'start': '2026-10-11', 'end': None}
        self.assertEqual(self.selected(self.capture(bounds=next_day, day=date(2026, 10, 11))), [])

    def test_earlier_start_and_later_or_unbounded_end_need_processing(self):
        self.publish(self.capture(), start=date(2026, 10, 11), end=date(2026, 10, 20))
        for bounds in [self.bounds, {'start': '2026-10-11', 'end': '2026-10-21'},
                       {'start': '2026-10-11', 'end': None}]:
            with self.subTest(bounds=bounds):
                run = self.capture(bounds=bounds)
                self.assertEqual(self.selected(run), ['A', 'B'])
                self.assertEqual(set(run.sheets.values_list('selection_reason', flat=True)), {'range'})
        self.assertEqual(self.selected(self.capture(bounds={'start': '2026-10-12', 'end': '2026-10-19'})), [])

    def test_unpublished_new_content_is_retried(self):
        self.publish(self.capture())
        rows = {'A': [['changed']], 'B': self.rows['B']}
        failed = self.capture(rows=rows)
        ParseAttempt.objects.create(run=failed, status='failed', error_type='ValueError')
        self.assertEqual(self.selected(self.capture(rows=rows)), ['A'])

    def test_source_identity_manifest_year_and_force_invalidate_skip(self):
        self.publish(self.capture())
        self.assertEqual(self.selected(self.capture(force=True)), ['A', 'B'])
        self.assertEqual(self.selected(self.capture(manifest={'release': 'new'})), ['A', 'B'])
        self.assertEqual(self.selected(self.capture(day=date(2027, 1, 1))), ['A', 'B'])
        self.source.sheet_gids['A'] = 99
        self.source.save()
        self.assertEqual(self.selected(self.capture()), ['A'])
        self.source.spreadsheet_id = 'other-book'
        self.source.save()
        self.assertEqual(self.selected(self.capture()), ['A', 'B'])

    def test_manual_capture_still_parses_all_sheets(self):
        self.publish(self.capture())
        now = timezone.now()
        manual = record_inputs(source_id=self.source.pk, sheets=self.rows,
            captured_at=now, reference_date=date(2026, 10, 10), knowledge_as_of=now,
            parser_manifest=self.manifest)
        self.assertEqual(self.selected(manual), ['A', 'B'])

    @override_settings(TABLEPARSER_RUNTIME={'resource_root': 'unused', 'catalog_source': 'test'})
    def test_unchanged_chain_completes_without_parser_publication_or_delivery(self):
        from contextlib import ExitStack
        self.publish(self.capture())
        with ExitStack() as stack:
            stack.enter_context(patch('schedule_ingestion.acquisition.runtime_manifest', return_value=self.manifest))
            stack.enter_context(patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=list(self.rows.values())))
            stack.enter_context(patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=date(2026, 10, 10)))
            calls = [stack.enter_context(patch(target)) for target in [
                'schedule_ingestion.tasks.execute_parse',
                'schedule_ingestion.publication.prepare_publication',
                'schedule_ingestion.delivery.deliver_publication']]
            result = source_refresh_chain(self.source.pk).apply(throw=True).get()
        self.assertEqual(result['status'], 'unchanged')
        for call in calls:
            call.assert_not_called()
        self.assertEqual(Publication.objects.count(), 1)
        self.assertEqual(ExportRevision.objects.count(), 1)
        self.assertFalse(ParseAttempt.objects.exists())

    def test_direct_parse_of_skipped_run_cannot_create_empty_export(self):
        from schedule_ingestion.parse_execution import execute_parse
        self.publish(self.capture())
        run = self.capture()
        # execute_parse intentionally rejects a surrounding test transaction first.
        with patch('schedule_ingestion.parse_execution.connections') as connections:
            connections.__getitem__.return_value.in_atomic_block = False
            connections.__getitem__.return_value.get_autocommit.return_value = True
            with self.assertRaisesRegex(ValueError, 'No sheets selected'):
                execute_parse(run.pk, resource_root='unused', catalog_source='test')
        self.assertFalse(run.exports.exists())

    def test_duplicate_capture_keeps_selection_and_rejects_changed_range(self):
        from schedule_ingestion.acquisition import acquire_source
        first = self.capture()
        self.publish(first)
        with patch('schedule_ingestion.acquisition.fetch_sheet') as fetch:
            retry = acquire_source(self.source.pk, acquisition_id=first.acquisition_id,
                resource_root='unused', catalog_source='test', resolved_range=self.bounds)
            self.assertEqual(self.selected(retry), ['A', 'B'])
            with self.assertRaisesRegex(ValueError, 'options changed'):
                acquire_source(self.source.pk, acquisition_id=first.acquisition_id,
                    resource_root='unused', catalog_source='test', resolved_range={'start': '2026-10-11', 'end': None})
            fetch.assert_not_called()


class PartialPublicationTests(TransactionTestCase):
    def setUp(self):
        from schedule_ingestion.tests.test_parse_execution import ParseExecutionTests
        ParseExecutionTests.setUp(self)
        self.source.sheet_names = ['First', 'Second']
        self.source.sheet_gids = {'First': 1, 'Second': 2}
        self.source.save()

    def test_empty_changed_group_is_cleaned_unchanged_group_is_untouched(self):
        from contextlib import ExitStack
        from scheduler.models import Group, Lesson
        from schedule_ingestion.run_storage import load_export
        Group.objects.create(title='А')
        Group.objects.create(title='Б')
        sheets = {
            1: [[], ['', '', 'А'], ['07.10.2026', '1', 'Физика']],
            2: [[], ['', '', 'Б'], ['07.10.2026', '1', 'История']],
        }
        def notified(summary):
            return dict(summary, notification_summary={'type': 'NotificationSummary',
                'success_count': 0, 'failed_count': 0, 'blocked_chat_ids': []})
        with ExitStack() as stack:
            stack.enter_context(override_settings(TABLEPARSER_RUNTIME={
                'resource_root': str(self.root), 'catalog_source': self.catalog_source}))
            stack.enter_context(patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=lambda book, gid: sheets[gid]))
            stack.enter_context(patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=date(2026, 10, 7)))
            notify = stack.enter_context(patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run', side_effect=notified))
            report = stack.enter_context(patch('scheduler.tasks.notification.deliver_admin_report', return_value=({}, {'success_count': 1})))
            first_id = source_refresh_chain(self.source.pk).apply(throw=True).get()
            self.assertEqual(Lesson.objects.count(), 2)
            untouched_pk = Lesson.objects.get(group__title='Б').pk
            sheets[1] = [[], ['', '', 'А'], ['07.10.2026', '1', '']]
            second_id = source_refresh_chain(self.source.pk).apply(throw=True).get()
            second = Publication.objects.get(pk=second_id)
            export = load_export(second.revision_id)
            self.assertEqual(export['groups'], ['А'])
            self.assertEqual(export['lessons'], [])
            self.assertEqual(list(Lesson.objects.values_list('pk', flat=True)), [untouched_pk])
            self.assertEqual(second.revision.run.sheets.filter(selected=True).get().name, 'First')
            unchanged = source_refresh_chain(self.source.pk).apply(throw=True).get()
            self.assertEqual(unchanged['status'], 'unchanged')
            self.assertEqual(Publication.objects.count(), 2)
            self.assertEqual(notify.call_count, 2)
            self.assertEqual(report.call_count, 2)
            self.assertNotEqual(first_id, second_id)
