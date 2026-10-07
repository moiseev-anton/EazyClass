from datetime import date, timedelta
import uuid
from unittest import skipUnless
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import orjson
from django.apps import apps
from django.db import connection, connections
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from schedule_ingestion.models import ScheduleSource, Publication, ScheduleWriteEvent, Confirmation, Observation
from schedule_ingestion.run_storage import record_inputs, save_export


@skipUnless(apps.is_installed('scheduler'), 'Requires scheduler models')
class PublicationTests(TestCase):
    def setUp(self):
        from scheduler.models import Group, Teacher
        self.group = Group.objects.create(title='А-1')
        self.other = Group.objects.create(title='Б-2')
        Teacher.objects.create(full_name='Иванов Иван Иванович', short_name='Иванов И.И.', is_active=False)
        self.source = ScheduleSource.objects.create(name='Test', spreadsheet_id='id', sheet_names=['Sheet'])
        self.today = date(2026, 10, 7)
        clock = patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=self.today)
        clock.start()
        self.addCleanup(clock.stop)

    def version(self, lessons=None, captured_at=None, groups=None):
        run = record_inputs(source_id=self.source.pk, sheets={'Sheet': []},
            captured_at=captured_at or timezone.now(), reference_date=self.today,
            knowledge_as_of=timezone.now(), parser_manifest={'test': True})
        return save_export(run_id=run.pk, expected_revision=0, request_id=uuid.uuid4(),
            groups=groups or ['А-1'], lessons=lessons if lessons is not None else [self.lesson()],
            review_items=[], author='test')

    def lesson(self, **values):
        row = dict(group='А-1', date='2026-10-08', lesson_number=1, part=0, subgroup=0,
            subject='Физика', teacher='Иванов И.И.', classroom='100', review_status='needs_review',
            annotations=[{'text': 'Лекция'}])
        row.update(values)
        return row

    def prepare(self, version, **options):
        from schedule_ingestion.publication import prepare_publication
        return prepare_publication(version.pk, requested_by='admin', **options)

    def apply(self, publication):
        from schedule_ingestion.publication import apply_publication
        return apply_publication(publication.pk)

    def test_needs_review_part_subgroup_annotations_and_inactive_teacher(self):
        from scheduler.models import Lesson
        publication = self.prepare(self.version([self.lesson(part=1, subgroup=2)]))
        with patch('utils.RedisClientManager.get_client', side_effect=AssertionError('No Redis')):
            result = self.apply(publication)
        row = Lesson.objects.select_related('teacher', 'annotation', 'period').get()
        self.assertEqual(row.teacher.full_name, 'Иванов Иван Иванович')
        self.assertEqual(row.annotation.title, 'Лекция')
        self.assertEqual((row.period.part, row.subgroup), (1, '2'))
        self.assertEqual(result.status, 'applied')
        self.assertEqual(len(result.summary['added']), 1)
        self.assertFalse(Confirmation.objects.exists())
        self.assertFalse(Observation.objects.exists())
        self.assertEqual(self.apply(publication).summary, result.summary)
        self.assertEqual(ScheduleWriteEvent.objects.count(), 1)

    def test_full_requested_range_removes_november_but_not_other_groups_or_past(self):
        from scheduler.models import Lesson, Period
        november = Period.objects.create(date=date(2026, 11, 2), lesson_number=1)
        past = Period.objects.create(date=date(2026, 10, 6), lesson_number=1)
        doomed = Lesson.objects.create(group=self.group, period=november)
        other = Lesson.objects.create(group=self.other, period=november)
        kept = Lesson.objects.create(group=self.group, period=past)
        result = self.apply(self.prepare(self.version()))
        self.assertFalse(Lesson.objects.filter(pk=doomed.pk).exists())
        self.assertTrue(Lesson.objects.filter(pk__in=[other.pk, kept.pk]).count() == 2)
        self.assertEqual(len(result.summary['removed']), 1)

    def test_bounded_empty_export_cleans_only_declared_dates(self):
        from scheduler.models import Lesson, Period
        for day in (self.today, self.today + timedelta(days=1)):
            Lesson.objects.create(group=self.group, period=Period.objects.create(date=day, lesson_number=1))
        result = self.apply(self.prepare(self.version([]), end_day_offset=0))
        self.assertEqual(len(result.summary['removed']), 1)
        self.assertEqual(Lesson.objects.get().period.date, self.today + timedelta(days=1))

    def test_old_automatic_is_superseded_but_explicit_manual_can_replace_newer(self):
        from scheduler.models import Lesson
        old = self.version([self.lesson(subject='Старая')], captured_at=timezone.now() - timedelta(days=1))
        late = self.prepare(old, automatic=True)
        self.apply(self.prepare(self.version([self.lesson(subject='Новая')]), automatic=True))
        self.assertEqual(self.apply(late).status, 'superseded')
        self.assertEqual(Lesson.objects.get().subject.title, 'Новая')
        manual = self.apply(self.prepare(old))
        self.assertEqual(Lesson.objects.get().subject.title, 'Старая')
        self.assertEqual(len(manual.summary['updated']), 1)

    def test_legacy_sync_prevents_late_automatic_overwrite(self):
        from scheduler.fetched_data_sync.lessons.lessons_sync_manager import LessonsSyncManager
        from enums import KeyEnum
        version = self.version(captured_at=timezone.now() - timedelta(hours=1))
        publication = self.prepare(version, automatic=True)
        client = Mock()
        values = {KeyEnum.SCRAPED_LESSONS: orjson.dumps([]),
            KeyEnum.SCRAPED_GROUPS: orjson.dumps({str(self.group.pk): 'hash'}),
            KeyEnum.UNCHANGED_GROUPS: orjson.dumps([])}
        client.get.side_effect = values.get
        LessonsSyncManager(client, start_sync_day=self.today).update_schedule()
        self.assertEqual(self.apply(publication).status, 'superseded')

    def test_failure_rolls_back_schedule_event_and_status(self):
        from scheduler.models import Lesson
        publication = self.prepare(self.version())
        original = Publication.save
        def failing(instance, *args, **kwargs):
            if instance.status == 'applied':
                raise RuntimeError('failure')
            return original(instance, *args, **kwargs)
        with patch.object(Publication, 'save', failing), self.assertRaises(RuntimeError):
            self.apply(publication)
        self.assertFalse(Lesson.objects.exists())
        self.assertFalse(ScheduleWriteEvent.objects.exists())
        publication.refresh_from_db()
        self.assertEqual(publication.status, 'pending')

    def test_unknown_group_invalid_lesson_and_ambiguous_group_stop_preparation(self):
        from scheduler.models import Group
        from schedule_ingestion.publication import prepare_publication
        invalid = self.version([self.lesson(date='not-a-date')])
        with self.assertRaises(ValueError):
            self.prepare(invalid)
        unknown = self.version([], groups=['Нет'])
        with self.assertRaises(ValueError):
            self.prepare(unknown)
        Group.objects.create(title='А1')
        with self.assertRaises(ValueError):
            prepare_publication(self.version().pk, requested_by='admin')
        self.assertFalse(Publication.objects.exists())

    def test_preparation_retry_keeps_dates_and_rejects_changed_request(self):
        version, key = self.version(), uuid.uuid4()
        first = self.prepare(version, request_id=key, start_day_offset=1)
        with patch('scheduler.dtos.lesson_sync_range.timezone.localdate', return_value=date(2026, 10, 9)):
            second = self.prepare(version, request_id=key, start_day_offset=1)
        self.assertEqual((second.pk, second.start_date), (first.pk, date(2026, 10, 8)))
        with self.assertRaises(ValueError):
            self.prepare(version, request_id=key, start_day_offset=0)


@skipUnless(apps.is_installed('scheduler') and connection.vendor == 'postgresql', 'PostgreSQL publication locks')
class ConcurrentPublicationTests(TransactionTestCase):
    setUp = PublicationTests.setUp
    version = PublicationTests.version
    lesson = PublicationTests.lesson
    prepare = PublicationTests.prepare

    def test_duplicate_delivery_applies_once(self):
        from schedule_ingestion.publication import apply_publication
        from scheduler.models import Lesson
        publication = self.prepare(self.version())
        barrier = Barrier(2)
        def apply(_):
            try:
                barrier.wait(timeout=10)
                return apply_publication(publication.pk).summary
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            summaries = list(pool.map(apply, range(2)))
        self.assertEqual(summaries[0], summaries[1])
        self.assertEqual(Lesson.objects.count(), 1)
        self.assertEqual(ScheduleWriteEvent.objects.count(), 1)

    def test_shared_guard_is_transactional_and_excludes_other_connections(self):
        import psycopg2
        from scheduler.schedule_write_guard import schedule_write_guard
        other = psycopg2.connect(**connection.get_connection_params())
        try:
            with schedule_write_guard():
                with other, other.cursor() as cursor:
                    cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [734921650812])
                    self.assertFalse(cursor.fetchone()[0])
            with other, other.cursor() as cursor:
                cursor.execute('SELECT pg_try_advisory_xact_lock(%s)', [734921650812])
                self.assertTrue(cursor.fetchone()[0])
        finally:
            other.close()
