"""Opt-in integration with a disposable Redis broker and PostgreSQL database."""
import os
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import Mock, patch

from celery import Celery, chain, current_app, signals
from celery import _state
from celery.contrib.testing.worker import start_worker
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone


@skipUnless(os.environ.get('TABLEPARSER_TEST_REDIS_PORT'), 'Requires disposable Redis')
class BrokerWorkerTests(TransactionTestCase):
    def setUp(self):
        # Refuse to run this integration suite against the application's database.
        self.assertEqual(connection.vendor, 'postgresql')
        self.assertEqual(connection.settings_dict['HOST'], '127.0.0.1')
        self.assertEqual(connection.settings_dict['NAME'], 'test_tableparser_validation')
        from schedule_ingestion.tests.test_parse_execution import ParseExecutionTests
        from scheduler.models import Group
        ParseExecutionTests.setUp(self)
        Group.objects.create(title='А')
        self.source.sheet_gids = {'Sheet': 0}
        self.source.save()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(override_settings(TABLEPARSER_RUNTIME={
            'resource_root': str(self.root), 'catalog_source': self.catalog_source}))
        self.fetch = self.stack.enter_context(patch('schedule_ingestion.acquisition.fetch_sheet',
            return_value=[[], ['', '', 'А'], [timezone.localdate().strftime('%d.%m.%Y'), '1', 'Физика']]))
        self.notify = Mock(
            side_effect=lambda summary: dict(summary, notification_summary={
                'type': 'NotificationSummary', 'success_count': 1,
                'failed_count': 0, 'blocked_chat_ids': []}))
        self.stack.enter_context(patch(
            'scheduler.tasks.notification.send_lessons_refresh_notifications',
            new=SimpleNamespace(run=self.notify)))
        self.report = self.stack.enter_context(patch(
            'scheduler.tasks.notification.deliver_admin_report',
            return_value=({}, {'success_count': 1})))
        port = int(os.environ['TABLEPARSER_TEST_REDIS_PORT'])
        previous_app = current_app._get_current_object()
        previous_default = _state.default_app
        self.stack.callback(previous_app.set_current)
        self.stack.callback(_state.set_default_app, previous_default)
        self.app = Celery('tableparser_worker_validation',
            broker=f'redis://127.0.0.1:{port}/0', backend=f'redis://127.0.0.1:{port}/1')
        self.stack.callback(self.app.close)
        self.app.conf.update(task_always_eager=False, task_serializer='json',
            result_serializer='json', accept_content=['json'], result_expires=300,
            worker_prefetch_multiplier=1, broker_connection_retry_on_startup=False)
        # Shared task registration is real; only the external input and senders are replaced.
        import schedule_ingestion.tasks  # noqa: F401
        self.app.finalize()
        # Embedded worker connections belong to its thread, not the test thread.
        def close_worker_connections(**kwargs):
            connections.close_all()
        signals.task_postrun.connect(close_worker_connections, weak=False)
        self.stack.callback(signals.task_postrun.disconnect, close_worker_connections)

    def worker(self):
        return start_worker(self.app, pool='solo', concurrency=1, queues=['periodic_tasks'],
            perform_ping_check=False, shutdown_timeout=30, loglevel='ERROR')

    def test_full_chain_and_replayed_publication_across_worker_restart(self):
        from schedule_ingestion.tasks import source_refresh_chain
        from schedule_ingestion.models import Publication, PublicationDelivery, ParseAttempt
        from scheduler.models import Lesson
        workflow = source_refresh_chain(self.source.pk)
        with self.worker():
            publication_id = workflow.apply_async().get(timeout=60)
        publication = Publication.objects.get(pk=publication_id)
        self.assertEqual(publication.status, 'applied')
        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(ParseAttempt.objects.get().status, 'succeeded')
        self.assertEqual(PublicationDelivery.objects.filter(status='completed').count(), 2)
        # Restart the worker, then resend the same publication request through the broker.
        replay = chain(*(task.clone() for task in list(workflow.tasks)[2:]))
        with self.worker():
            self.assertEqual(replay.apply_async(args=(str(publication.revision_id),)).get(timeout=60),
                             publication_id)
        self.assertEqual(Publication.objects.count(), 1)
        self.assertEqual(Lesson.objects.count(), 1)
        self.fetch.assert_called_once()
        self.notify.assert_called_once()
        self.report.assert_called_once()

    def test_uncertain_send_stops_chain_and_broker_replay_does_not_resend(self):
        from schedule_ingestion.tasks import source_refresh_chain, notify_publication
        from schedule_ingestion.models import Publication, PublicationDelivery
        self.notify.side_effect = RuntimeError('Simulated uncertain delivery')
        with self.worker():
            with self.assertRaisesRegex(RuntimeError, 'Simulated uncertain delivery'):
                source_refresh_chain(self.source.pk).apply_async().get(timeout=60)
            publication = Publication.objects.get()
            # Read result through the real backend: custom error must survive serialization.
            result = notify_publication.apply_async(args=(str(publication.pk),))
            error = result.get(timeout=60, propagate=False)
            self.assertEqual(type(error).__name__, 'DeliveryUncertain')
        self.assertEqual(PublicationDelivery.objects.get(phase='notifications').status, 'uncertain')
        self.assertEqual(PublicationDelivery.objects.get(phase='report').status, 'pending')
        self.notify.assert_called_once()
        self.report.assert_not_called()

    def tearDown(self):
        connections.close_all()
        super().tearDown()
