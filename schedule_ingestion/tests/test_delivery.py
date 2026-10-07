from datetime import date
from types import SimpleNamespace
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.test import TestCase, SimpleTestCase, TransactionTestCase, override_settings

from schedule_ingestion.models import PublicationDelivery
from schedule_ingestion.tests.test_publication import PublicationTests


@skipUnless(apps.is_installed('django_celery_beat'), 'Requires publication_settings')
class DeliveryTests(TestCase):
    setUp = PublicationTests.setUp
    version = PublicationTests.version
    lesson = PublicationTests.lesson
    prepare = PublicationTests.prepare
    apply = PublicationTests.apply

    def notified(self, summary):
        return dict(summary, notification_summary={'type': 'NotificationSummary', 'success_count': 2,
            'failed_count': 1, 'blocked_chat_ids': []})

    def test_success_and_partial_delivery_are_not_resent(self):
        from schedule_ingestion.delivery import deliver_publication
        publication = self.apply(self.prepare(self.version()))
        with patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run', side_effect=self.notified) as send:
            first = deliver_publication(publication.pk, 'notifications')
            self.assertEqual(deliver_publication(publication.pk, 'notifications'), first)
            send.assert_called_once()
        self.assertEqual(first['notification_summary']['failed_count'], 1)
        with patch('scheduler.tasks.notification.deliver_admin_report', return_value=({}, {'success_count': 1})) as report:
            deliver_publication(publication.pk, 'report')
            deliver_publication(publication.pk, 'report')
            report.assert_called_once()
            summary = report.call_args.args[0]
            self.assertEqual(summary['publication']['id'], str(publication.pk))
            self.assertEqual(summary['publication']['needs_review_count'], 1)
            from scheduler.dtos import PipelineSummary
            message = PipelineSummary.deserialize(summary).to_message()
            self.assertIn(str(publication.revision_id), message)
            self.assertIn('ошибки=1', message)

    def test_send_error_is_uncertain_and_retry_does_not_send_again(self):
        from schedule_ingestion.delivery import deliver_publication, DeliveryUncertain
        publication = self.apply(self.prepare(self.version()))
        with patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run', side_effect=RuntimeError('private')) as send:
            with self.assertRaises(RuntimeError):
                deliver_publication(publication.pk, 'notifications')
            with self.assertRaises(DeliveryUncertain):
                deliver_publication(publication.pk, 'notifications')
            send.assert_called_once()
        row = PublicationDelivery.objects.get(publication=publication, phase='notifications')
        self.assertEqual((row.status, row.error_type), ('uncertain', 'RuntimeError'))
        with self.assertRaises(DeliveryUncertain):
            deliver_publication(publication.pk, 'report')

    def test_superseded_publication_skips_subscribers_but_reports(self):
        from schedule_ingestion.delivery import deliver_publication
        from django.utils import timezone
        from datetime import timedelta
        old = self.prepare(self.version(captured_at=timezone.now() - timedelta(days=1)), automatic=True)
        self.apply(self.prepare(self.version()))
        publication = self.apply(old)
        with patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run') as send:
            deliver_publication(publication.pk, 'notifications')
            send.assert_not_called()
        with patch('scheduler.tasks.notification.deliver_admin_report', return_value=({}, {})) as report:
            deliver_publication(publication.pk, 'report')
            self.assertEqual(report.call_args.args[0]['publication']['status'], 'superseded')

    def test_publication_chain_uses_existing_tasks_and_retry_has_no_effects(self):
        from schedule_ingestion.tasks import publication_chain
        from scheduler.models import Lesson
        version = self.version()
        workflow = publication_chain(version.pk, requested_by='admin')
        with patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run', side_effect=self.notified) as notify:
            with patch('scheduler.tasks.notification.deliver_admin_report', return_value=({}, {})) as report:
                result = workflow.apply(throw=True).get()
                self.assertEqual(workflow.apply(throw=True).get(), result)
                notify.assert_called_once()
                report.assert_called_once()
        self.assertEqual(Lesson.objects.count(), 1)

    @override_settings(TABLEPARSER_PUBLIC_BASE_URL='https://example.invalid')
    def test_report_link_is_to_readonly_publication_history(self):
        from schedule_ingestion.delivery import pipeline_summary
        from scheduler.dtos import PipelineSummary
        publication = self.apply(self.prepare(self.version()))
        path = '/admin/schedule_ingestion/publication/' + str(publication.pk) + '/change/'
        with patch('schedule_ingestion.delivery.reverse', return_value=path):
            summary = pipeline_summary(publication)
        self.assertEqual(summary['publication']['url'], 'https://example.invalid' + path)
        self.assertIn('Открыть публикацию', PipelineSummary.deserialize(summary).to_message())


class PublicationChainRangeTests(SimpleTestCase):
    def test_range_is_resolved_before_fetch_and_signatures_only_carry_ids(self):
        from schedule_ingestion.tasks import source_refresh_chain
        with patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=date(2026, 10, 7)):
            workflow = source_refresh_chain(42, start_day_offset=1)
        tasks = list(workflow.tasks)
        self.assertEqual(tasks[0].args, (42,))
        self.assertEqual(tasks[2].kwargs['resolved_range'], {'start': '2026-10-08', 'end': None})
        self.assertEqual(tasks[2].kwargs['automatic'], True)
        self.assertEqual(tasks[3].task, 'schedule_ingestion.tasks.notify_publication')
        self.assertEqual(tasks[4].task, 'schedule_ingestion.tasks.report_publication')


@skipUnless(apps.is_installed('django_celery_beat'), 'Requires publication_settings')
class FullRefreshTests(TransactionTestCase):
    def setUp(self):
        from schedule_ingestion.tests.test_parse_execution import ParseExecutionTests
        ParseExecutionTests.setUp(self)

    def test_fetch_parse_publish_notify_report_chain(self):
        from scheduler.models import Group, Lesson
        from schedule_ingestion.tasks import source_refresh_chain
        from schedule_ingestion.models import Publication
        Group.objects.create(title='А')
        self.source.sheet_gids = {'Sheet': 0}
        self.source.save()
        def notified(summary):
            return dict(summary, notification_summary={'type': 'NotificationSummary',
                'success_count': 1, 'failed_count': 0, 'blocked_chat_ids': []})
        with override_settings(TABLEPARSER_RUNTIME={'resource_root': str(self.root), 'catalog_source': self.catalog_source}):
            with patch('schedule_ingestion.acquisition.fetch_sheet',
                       return_value=[[], ['', '', 'А'], ['07.10.2026', '1', 'Физика']]):
                with patch('scheduler.tasks.notification.send_lessons_refresh_notifications.run', side_effect=notified) as notify:
                    with patch('scheduler.tasks.notification.deliver_admin_report', return_value=({}, {'success_count': 1})) as report:
                        with patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=date(2026, 10, 7)):
                            result = source_refresh_chain(self.source.pk).apply(throw=True).get()
        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(Publication.objects.get(pk=result).status, 'applied')
        self.assertEqual(PublicationDelivery.objects.filter(status='completed').count(), 2)
        notify.assert_called_once()
        report.assert_called_once()
