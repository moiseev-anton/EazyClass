import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.core.management import call_command, CommandError
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from schedule_ingestion.delivery_recovery import resolve_delivery
from schedule_ingestion.models import DeliveryResolution, PublicationDelivery
from schedule_ingestion.tests import test_publication as fixtures


@skipUnless(apps.is_installed('django_celery_beat'), 'Requires publication settings')
class RecoveryTests(TestCase):
    setUp = fixtures.PublicationTests.setUp
    version = fixtures.PublicationTests.version
    lesson = fixtures.PublicationTests.lesson
    prepare = fixtures.PublicationTests.prepare
    apply = fixtures.PublicationTests.apply

    def ambiguous(self, status='uncertain'):
        publication = self.apply(self.prepare(self.version()))
        delivery = publication.deliveries.get(phase='notifications')
        delivery.status, delivery.token = status, uuid.uuid4()
        delivery.started_at = timezone.now()
        delivery.error_type = 'RuntimeError'
        delivery.save()
        return publication, delivery

    def resolve(self, publication, delivery, **kwargs):
        options = dict(request_id=uuid.uuid4(), expected_token=delivery.token,
            decision='retry', actor='operator', reason='Checked sender outcome')
        options.update(kwargs)
        return resolve_delivery(publication.pk, delivery.phase, **options)

    def test_retry_is_audited_and_identical_request_is_idempotent(self):
        publication, delivery = self.ambiguous()
        request_id = uuid.uuid4()
        resolution = self.resolve(publication, delivery, request_id=request_id)
        self.assertEqual(self.resolve(publication, delivery, request_id=request_id).pk, resolution.pk)
        current = PublicationDelivery.objects.get(pk=delivery.pk)
        self.assertEqual(current.status, 'pending')
        self.assertIsNone(current.token)
        self.assertEqual(resolution.previous['token'], str(delivery.token))
        self.assertEqual(resolution.previous['error_type'], 'RuntimeError')
        self.assertEqual(DeliveryResolution.objects.count(), 1)
        with self.assertRaises(ValueError):
            self.resolve(publication, delivery, request_id=request_id, decision='skip')
        with self.assertRaises(ValueError):
            self.resolve(publication, delivery)

    def test_running_sender_requires_explicit_stop_and_old_token_is_fenced(self):
        publication, delivery = self.ambiguous('sending')
        with self.assertRaisesRegex(ValueError, 'stopped'):
            self.resolve(publication, delivery)
        self.assertFalse(DeliveryResolution.objects.exists())
        self.resolve(publication, delivery, worker_stopped=True)
        self.assertEqual(PublicationDelivery.objects.filter(pk=delivery.pk,
            status='sending', token=delivery.token).update(status='completed'), 0)

    def test_stale_token_and_finished_delivery_cannot_be_reset(self):
        publication, delivery = self.ambiguous()
        with self.assertRaises(ValueError):
            self.resolve(publication, delivery, expected_token=uuid.uuid4())
        for status in ('pending', 'completed', 'skipped'):
            PublicationDelivery.objects.filter(pk=delivery.pk).update(status=status)
            with self.assertRaises(ValueError):
                self.resolve(publication, delivery)
        self.assertFalse(DeliveryResolution.objects.exists())

    def test_resolution_and_status_are_one_transaction(self):
        publication, delivery = self.ambiguous()
        with patch.object(PublicationDelivery, 'save', side_effect=RuntimeError('Failed update')):
            with self.assertRaises(RuntimeError):
                self.resolve(publication, delivery)
        self.assertFalse(DeliveryResolution.objects.exists())
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, 'uncertain')

    def test_skip_resumes_report_without_resending_and_report_marks_skip(self):
        from schedule_ingestion.tasks import resume_publication_chain
        from scheduler.dtos import PipelineSummary
        from scheduler.models import Lesson
        publication, delivery = self.ambiguous()
        self.resolve(publication, delivery, decision='skip')
        with patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run') as notify:
            with patch('scheduler.tasks.notification.deliver_admin_report', return_value=({}, {})) as report:
                for _ in range(2):
                    self.assertEqual(resume_publication_chain(publication.pk).apply(throw=True).get(), str(publication.pk))
                notify.assert_not_called()
                report.assert_called_once()
                self.assertIn('доставка не подтверждена',
                    PipelineSummary.deserialize(report.call_args.args[0]).to_message())
        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(PublicationDelivery.objects.get(publication=publication, phase='report').status, 'completed')

    def test_commands_inspect_before_enqueue_and_resolve_without_sending(self):
        publication, delivery = self.ambiguous()
        with patch('schedule_ingestion.tasks.resume_publication_chain') as enqueue:
            call_command('resume_publication', str(publication.pk), stdout=io.StringIO())
            with self.assertRaises(CommandError):
                call_command('resume_publication', str(publication.pk), enqueue=True, stdout=io.StringIO())
            enqueue.assert_not_called()
            call_command('resolve_publication_delivery', str(publication.pk), phase='notifications',
                decision='retry', request_id=uuid.uuid4(), expected_token=delivery.token,
                actor='admin', reason='Sender stopped and no messages sent', stdout=io.StringIO())
            enqueue.assert_not_called()
            enqueue.return_value.apply_async.return_value.id = 'test-task'
            call_command('resume_publication', str(publication.pk), enqueue=True, stdout=io.StringIO())
            enqueue.assert_called_once_with(publication.pk)

    def test_authorized_retry_sends_once_and_keeps_original_publication_range(self):
        from datetime import date
        from schedule_ingestion.tasks import resume_publication_chain
        from scheduler.models import Lesson
        publication, delivery = self.ambiguous()
        self.resolve(publication, delivery)
        def notified(summary):
            return dict(summary, notification_summary={'type': 'NotificationSummary',
                'success_count': 1, 'failed_count': 0, 'blocked_chat_ids': []})
        with patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=date(2099, 1, 1)):
            with patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run', side_effect=notified) as notify:
                with patch('scheduler.tasks.notification.deliver_admin_report', return_value=({}, {})) as report:
                    for _ in range(2):
                        resume_publication_chain(publication.pk).apply(throw=True).get()
                    notify.assert_called_once()
                    report.assert_called_once()
                    self.assertEqual(report.call_args.args[0]['publication']['start'], publication.start_date.isoformat())
        self.assertEqual(Lesson.objects.count(), 1)


@skipUnless(apps.is_installed('django_celery_beat') and connection.vendor == 'postgresql', 'Requires PostgreSQL')
class ConcurrentRecoveryTests(TransactionTestCase):
    setUp = RecoveryTests.setUp
    version = RecoveryTests.version
    lesson = RecoveryTests.lesson
    prepare = RecoveryTests.prepare
    apply = RecoveryTests.apply
    ambiguous = RecoveryTests.ambiguous
    resolve = RecoveryTests.resolve

    def test_only_one_competing_operator_can_resolve_attempt(self):
        publication, delivery = self.ambiguous()
        barrier = Barrier(2)
        def attempt():
            try:
                barrier.wait(timeout=10)
                self.resolve(publication, delivery)
                return 'resolved'
            except ValueError:
                return 'stale'
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(lambda _: attempt(), range(2)))
        self.assertCountEqual(outcomes, ['resolved', 'stale'])
        self.assertEqual(DeliveryResolution.objects.count(), 1)
