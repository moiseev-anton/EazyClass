import json
import uuid
from datetime import date
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from kombu.exceptions import OperationalError

from schedule_ingestion.models import ExportRevision, Publication, Observation, Confirmation
from schedule_ingestion.run_storage import load_export, save_export
from schedule_ingestion.tests import test_publication as fixtures


@skipUnless(apps.is_installed('django.contrib.admin'), 'Requires admin_settings')
class AdminReviewTests(TestCase):
    version = fixtures.PublicationTests.version
    lesson = fixtures.PublicationTests.lesson

    def setUp(self):
        fixtures.PublicationTests.setUp(self)
        self.user = get_user_model().objects.create_superuser(username='review-admin', password='test-password')
        self.client.force_login(self.user)
        self.export = self.version([self.lesson(raw_cell='<script>bad()</script>'), self.lesson(lesson_number=2)])

    def url(self, name, *args):
        return reverse('admin:ingestion_' + name, args=[self.export.pk, *args])

    def edit_data(self, **values):
        data = dict(request_id=str(uuid.uuid4()), group='А-1', date='2026-10-08', lesson_number=1,
            part=0, subgroup=0, subject='Исправленный предмет', teacher='Иванов И.И.',
            classroom='100', annotation='Лекция', reviewed='on', reason='Проверена исходная ячейка')
        data.update(values)
        return data

    @override_settings(TABLEPARSER_RUNTIME={'resource_root': '/release/runtime', 'catalog_source': 'api'})
    def test_source_action_enqueues_parse_only_and_skips_disabled_sources(self):
        from schedule_ingestion.models import ScheduleSource
        disabled = ScheduleSource.objects.create(name='Disabled', spreadsheet_id='other', enabled=False)
        url = reverse('admin:schedule_ingestion_schedulesource_changelist')
        with patch('schedule_ingestion.tasks.source_parse_chain') as chain:
            chain.return_value.apply_async.return_value.id = 'test-task'
            response = self.client.post(url, {'action': 'load_sources', '_selected_action': [self.source.pk, disabled.pk]}, follow=True)
            self.assertContains(response, 'поставлен в очередь')
            self.assertContains(response, 'выключен')
            chain.assert_called_once_with(self.source.pk)
            chain.return_value.apply_async.assert_called_once_with()
        self.assertFalse(Publication.objects.exists())

    @override_settings(TABLEPARSER_RUNTIME=None)
    def test_source_action_rejects_missing_runtime(self):
        url = reverse('admin:schedule_ingestion_schedulesource_changelist')
        with patch('schedule_ingestion.tasks.source_parse_chain') as chain:
            response = self.client.post(url, {'action': 'load_sources', '_selected_action': [self.source.pk]}, follow=True)
            self.assertContains(response, 'не настроены')
            chain.assert_not_called()

    @override_settings(TABLEPARSER_RUNTIME={'resource_root': '/release/runtime', 'catalog_source': 'api'})
    def test_source_action_handles_broker_failure_and_requires_change_permission_and_csrf(self):
        url = reverse('admin:schedule_ingestion_schedulesource_changelist')
        data = {'action': 'load_sources', '_selected_action': [self.source.pk]}
        with patch('schedule_ingestion.tasks.source_parse_chain') as chain:
            chain.return_value.apply_async.side_effect = OperationalError('offline')
            response = self.client.post(url, data, follow=True)
            self.assertContains(response, 'Не удалось подтвердить')
            csrf_client = Client(enforce_csrf_checks=True)
            csrf_client.force_login(self.user)
            self.assertEqual(csrf_client.post(url, data).status_code, 403)
            viewer = get_user_model().objects.create(username='source-viewer', is_staff=True)
            viewer.user_permissions.add(Permission.objects.get(codename='view_schedulesource'))
            self.client.force_login(viewer)
            chain.reset_mock()
            self.client.post(url, data)
            chain.assert_not_called()

    def test_review_run_and_history_pages_render_with_escaped_cells(self):
        response = self.client.get(self.url('review') + '?needs_review=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['needs_review'], 2)
        edit = self.client.get(self.url('edit', 0))
        self.assertContains(edit, '&lt;script&gt;bad()&lt;/script&gt;')
        self.assertNotContains(edit, '<script>bad()</script>')
        for name, pk in [('parserun', self.export.run_id), ('exportrevision', self.export.pk)]:
            self.assertEqual(self.client.get(reverse(f'admin:schedule_ingestion_{name}_change', args=[pk])).status_code, 200)

    def test_save_whole_version_preserves_other_rows_and_does_not_publish_or_learn(self):
        original = load_export(self.export.pk)
        data = self.edit_data()
        response = self.client.post(self.url('edit', 0), data)
        self.assertEqual(response.status_code, 302)
        saved = ExportRevision.objects.get(number=2)
        payload = load_export(saved.pk)
        self.assertEqual(payload['lessons'][0]['subject'], data['subject'])
        self.assertEqual(payload['lessons'][0]['review_status'], 'reviewed')
        self.assertEqual(payload['lessons'][1], original['lessons'][1])
        self.assertEqual(payload['lessons'][0]['annotations'], original['lessons'][0]['annotations'])
        self.assertEqual(load_export(self.export.pk), original)
        self.assertFalse(Publication.objects.exists())
        self.assertFalse(Observation.objects.exists())
        self.assertFalse(Confirmation.objects.exists())
        self.assertEqual(self.client.post(self.url('edit', 0), data).status_code, 302)
        self.assertEqual(ExportRevision.objects.count(), 2)

    def test_stale_edit_retains_entered_values_and_does_not_overwrite(self):
        payload = load_export(self.export.pk)
        save_export(run_id=self.export.run_id, expected_revision=1, request_id=uuid.uuid4(),
                    author='other-admin', **payload)
        response = self.client.post(self.url('edit', 0), self.edit_data())
        self.assertContains(response, 'Уже сохранена новая версия')
        self.assertContains(response, 'Исправленный предмет')
        self.assertEqual(ExportRevision.objects.count(), 2)

    def test_delete_preserves_group_for_full_period_cleanup(self):
        self.export = self.version([self.lesson()])
        response = self.client.post(self.url('edit', 0), self.edit_data(remove='on'))
        self.assertEqual(response.status_code, 302)
        saved = self.export.run.exports.get(number=2)
        payload = load_export(saved.pk)
        self.assertEqual(payload['groups'], ['А-1'])
        self.assertEqual(payload['lessons'], [])

    def test_download_and_upload_complete_version(self):
        response = self.client.get(self.url('download'))
        payload = json.loads(response.content)
        payload['lessons'] = []
        response = self.client.post(self.url('upload'), dict(request_id=str(uuid.uuid4()), reason='Занятия отменены',
            file=SimpleUploadedFile('export.json', json.dumps(payload).encode())))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(load_export(ExportRevision.objects.get(number=2).pk)['lessons'], [])

    def test_invalid_upload_does_not_create_revision(self):
        response = self.client.post(self.url('upload'), dict(request_id=str(uuid.uuid4()), reason='test',
            file=SimpleUploadedFile('export.json', b'{"lessons":[]}')))
        self.assertContains(response, 'Нужна полная выгрузка')
        self.assertEqual(ExportRevision.objects.count(), 1)

    def preview(self):
        response = self.client.post(self.url('publish'), {'start_day_offset': 0, 'end_day_offset': ''})
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context['preview'])
        self.assertFalse(Publication.objects.exists())
        return response.context['confirmation']

    def test_publication_requires_preview_keeps_dates_and_accepts_needs_review(self):
        self.assertEqual(self.client.get(self.url('publish')).status_code, 200)
        token = self.preview()
        from scheduler.models import Lesson
        with patch('schedule_ingestion.tasks.resume_publication_chain') as chain:
            with patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=date(2099, 1, 1)):
                for _ in range(2):
                    self.assertEqual(self.client.post(self.url('publish'), {'confirmation': token}).status_code, 302)
        publication = Publication.objects.get()
        self.assertEqual(publication.start_date, self.today)
        self.assertIsNone(publication.end_date)
        self.assertEqual(publication.revision_id, self.export.pk)
        self.assertEqual(chain.call_args.args, (publication.pk,))
        self.assertFalse(Lesson.objects.exists())

    def test_queue_failure_keeps_prepared_publication_and_retry_identity(self):
        token = self.preview()
        with patch('schedule_ingestion.tasks.resume_publication_chain') as chain:
            chain.return_value.apply_async.side_effect = OperationalError('Broker unavailable')
            response = self.client.post(self.url('publish'), {'confirmation': token})
            self.assertContains(response, 'Публикация сохранена, но очередь недоступна')
            publication = Publication.objects.get()
            self.assertEqual(publication.status, 'pending')
            chain.return_value.apply_async.side_effect = None
            self.assertEqual(self.client.post(self.url('publish'), {'confirmation': token}).status_code, 302)
            self.assertEqual(Publication.objects.get().pk, publication.pk)

    def test_tampered_confirmation_is_rejected(self):
        self.preview()
        response = self.client.post(self.url('publish'), {'confirmation': 'tampered'})
        self.assertContains(response, 'Подтверждение недействительно')
        self.assertFalse(Publication.objects.exists())

    def test_view_permission_does_not_grant_review_or_publish(self):
        viewer = get_user_model().objects.create(username='viewer', is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(content_type__app_label='schedule_ingestion', codename='view_exportrevision'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(self.url('review')).status_code, 200)
        self.assertEqual(self.client.get(self.url('download')).status_code, 200)
        self.assertEqual(self.client.get(self.url('edit', 0)).status_code, 403)
        self.assertEqual(self.client.post(self.url('edit', 0), self.edit_data()).status_code, 403)
        self.assertEqual(self.client.get(self.url('publish')).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url('download')).status_code, 302)

    def test_post_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.user)
        client.get(self.url('edit', 0))
        self.assertEqual(client.post(self.url('edit', 0), self.edit_data()).status_code, 403)
        self.assertEqual(ExportRevision.objects.count(), 1)

    def test_review_permission_is_separate_from_publication(self):
        reviewer = get_user_model().objects.create(username='reviewer', is_staff=True)
        reviewer.user_permissions.add(*Permission.objects.filter(content_type__app_label='schedule_ingestion',
            codename__in=['view_exportrevision', 'review_export']))
        self.client.force_login(reviewer)
        self.assertEqual(self.client.post(self.url('edit', 0), self.edit_data()).status_code, 302)
        self.assertEqual(self.client.post(self.url('publish'), {'start_day_offset': 0}).status_code, 403)
        self.assertFalse(Publication.objects.exists())

    def test_signed_confirmation_cannot_be_used_by_another_admin(self):
        token = self.preview()
        other = get_user_model().objects.create_superuser(username='another-admin', password='test')
        self.client.force_login(other)
        response = self.client.post(self.url('publish'), {'confirmation': token})
        self.assertContains(response, 'Подтверждение недействительно')
        self.assertFalse(Publication.objects.exists())

    def test_source_form_requires_complete_distinct_sheet_mapping(self):
        from schedule_ingestion.admin_forms import SourceForm
        data = dict(name='Source', spreadsheet_id='sheet-id', enabled=True,
                    sheet_names=['Первый', 'Второй'], sheet_gids={'Первый': 0, 'Второй': 1})
        self.assertTrue(SourceForm(data=data).is_valid())
        data['sheet_gids'] = {'Первый': 0}
        self.assertFalse(SourceForm(data=data).is_valid())
