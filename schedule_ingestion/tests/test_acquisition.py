import json
import uuid
from datetime import datetime, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from unittest import skipUnless
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import connection, connections
from django.test import TestCase, SimpleTestCase, TransactionTestCase, override_settings

from schedule_ingestion.acquisition import acquire_source
from schedule_ingestion.google_sheets import decode_rows, fetch_sheet, SheetResponseError, SheetTransportError
from schedule_ingestion.models import ScheduleSource, ParseRun, SheetContent
from schedule_ingestion.run_storage import load_tables
from schedule_ingestion.tasks import source_parse_chain


def response(document):
    return '/*O_o*/\ngoogle.visualization.Query.setResponse(' + json.dumps(document) + ');'


class GoogleSheetTests(SimpleTestCase):
    def test_formatted_values_and_successful_empty_response(self):
        text = response({'status': 'ok', 'table': {'rows': [{'c': [None,
            {'v': 'Date(2028,0,2)', 'f': '02.01.2028'}, {'v': '  Физика\nИванов  '}, {'v': 2}]}]}})
        self.assertEqual(decode_rows(text), [['', '02.01.2028', 'Физика\nИванов', '2']])
        self.assertEqual(decode_rows(response({'status': 'ok', 'table': {'rows': []}})), [])

    def test_errors_and_malformed_rows_never_become_empty_success(self):
        for text in ('<html>login</html>', response({'status': 'error', 'errors': []}),
                     response({'status': 'ok', 'table': {}}),
                     response({'status': 'ok', 'table': {'rows': [{'c': 'bad'}]}}),
                     response({'status': 'ok', 'table': {'rows': [{'c': [False]}]}})):
            with self.subTest(text=text), self.assertRaises(SheetResponseError):
                decode_rows(text)

    def test_http_errors_and_timeouts_are_distinguished(self):
        import requests
        for status, exception in ((403, SheetResponseError), (429, SheetTransportError), (503, SheetTransportError)):
            result = MagicMock(status_code=status)
            result.__enter__.return_value = result
            with patch('schedule_ingestion.google_sheets.requests.get', return_value=result), self.assertRaises(exception):
                fetch_sheet('id', 0)
        with patch('schedule_ingestion.google_sheets.requests.get', side_effect=requests.Timeout('private URL')):
            with self.assertRaisesRegex(SheetTransportError, '^Sheet connection failed$'):
                fetch_sheet('id', 0)


class AcquisitionTests(TestCase):
    def setUp(self):
        self.source = ScheduleSource.objects.create(name='Test', spreadsheet_id='id',
            sheet_names=['First', 'Second'], sheet_gids={'First': 0, 'Second': 12})
        self.identity = uuid.uuid4()
        self.manifest_patch = patch('schedule_ingestion.acquisition.runtime_manifest', return_value={'release': 'test'})
        self.manifest_patch.start()
        self.addCleanup(self.manifest_patch.stop)

    def acquire(self, **kwargs):
        return acquire_source(self.source.pk, acquisition_id=kwargs.get('identity', self.identity),
                              resource_root='unused', catalog_source='test')

    def test_full_input_retry_deduplication_and_reference_date(self):
        # 22:30 UTC is already the next day in Europe/Moscow.
        stamp = datetime(2026, 12, 31, 22, 30, tzinfo=datetime_timezone.utc)
        with patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=[[['raw']], []]) as fetch:
            with patch('schedule_ingestion.acquisition.timezone.now', return_value=stamp):
                first = self.acquire()
        self.assertEqual(fetch.call_args_list[0].args, ('id', 0))
        self.assertEqual(fetch.call_args_list[1].args, ('id', 12))
        self.assertEqual(first.reference_date.isoformat(), '2027-01-01')
        with patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=AssertionError('No refetch')):
            self.assertEqual(self.acquire().pk, first.pk)
        with patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=[[['raw']], []]):
            second = self.acquire(identity=uuid.uuid4())
        self.assertEqual(SheetContent.objects.count(), 2)
        self.assertEqual([t.rows for t in load_tables(second.pk)], [[['raw']], []])
        self.assertEqual(ParseRun.objects.count(), 2)

    def test_partial_failure_creates_no_run_and_retry_fetches_every_sheet(self):
        with patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=[[['raw']], SheetTransportError('failed')]):
            with self.assertRaises(SheetTransportError):
                self.acquire()
        self.assertFalse(ParseRun.objects.exists())
        self.assertFalse(SheetContent.objects.exists())
        with patch('schedule_ingestion.acquisition.fetch_sheet', return_value=[]) as fetch:
            self.acquire()
        self.assertEqual(fetch.call_count, 2)

    def test_configuration_change_or_disable_discards_the_entire_fetch(self):
        for updates in ({'spreadsheet_id': 'new-id'}, {'sheet_gids': {'First': 99, 'Second': 12}}, {'enabled': False}):
            self.source.spreadsheet_id = 'id'
            self.source.sheet_gids = {'First': 0, 'Second': 12}
            self.source.enabled = True
            self.source.save()
            def changed(*args):
                ScheduleSource.objects.filter(pk=self.source.pk).update(**updates)
                return []
            with patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=changed):
                with self.assertRaises(ValueError):
                    self.acquire()
        self.assertFalse(ParseRun.objects.exists())

    def test_invalid_gid_configuration_fails_before_network(self):
        self.source.sheet_gids = {'First': 0}
        self.source.save()
        with patch('schedule_ingestion.acquisition.fetch_sheet') as fetch:
            with self.assertRaises(ValueError):
                self.acquire()
            fetch.assert_not_called()


@override_settings(TABLEPARSER_RUNTIME={'resource_root': 'runtime', 'catalog_source': 'api'})
class TaskChainTests(SimpleTestCase):
    def test_chain_passes_explicit_run_and_export_ids(self):
        run_id, export_id = uuid.uuid4(), uuid.uuid4()
        with patch('schedule_ingestion.tasks.acquire_source', return_value=SimpleNamespace(pk=run_id)) as acquire:
            with patch('schedule_ingestion.tasks.execute_parse', return_value=SimpleNamespace(pk=export_id)) as parse:
                result = source_parse_chain(42).apply(throw=True).get()
        self.assertEqual(result, str(export_id))
        self.assertEqual(acquire.call_args.args, (42,))
        uuid.UUID(acquire.call_args.kwargs['acquisition_id'])
        self.assertEqual(parse.call_args.args, (str(run_id),))

    def test_fetch_error_does_not_start_parser(self):
        with patch('schedule_ingestion.tasks.acquire_source', side_effect=SheetResponseError('invalid')):
            with patch('schedule_ingestion.tasks.execute_parse') as parse:
                with self.assertRaises(SheetResponseError):
                    source_parse_chain(42).apply(throw=True)
                parse.assert_not_called()


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL acquisition locking')
class ConcurrentAcquisitionTests(TransactionTestCase):
    def test_duplicate_delivery_commits_one_complete_run(self):
        source = ScheduleSource.objects.create(name='Test', spreadsheet_id='id',
            sheet_names=['Sheet'], sheet_gids={'Sheet': 0})
        key, barrier = uuid.uuid4(), Barrier(2)
        def fetch(*args):
            barrier.wait(timeout=10)
            return [['raw']]
        def acquire(_):
            try:
                return acquire_source(source.pk, acquisition_id=key,
                    resource_root='unused', catalog_source='test').pk
            finally:
                connections.close_all()
        with patch('schedule_ingestion.acquisition.fetch_sheet', side_effect=fetch):
            with patch('schedule_ingestion.acquisition.runtime_manifest', return_value={'release': 'test'}):
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results = list(pool.map(acquire, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(ParseRun.objects.count(), 1)
        self.assertEqual(ParseRun.objects.get().sheets.count(), 1)
