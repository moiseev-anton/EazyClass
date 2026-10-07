import json
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.db import connection, transaction
from django.test import TransactionTestCase

from schedule_ingestion.historical_catalogs import HistoricalCatalogReader
from schedule_ingestion.live_catalogs import load_live_catalogs, SUPPLEMENT_SOURCE
from schedule_ingestion.models import CatalogSnapshot, CatalogExclusionEvent


@skipUnless(apps.is_installed('scheduler'), 'Run with catalog_settings to include scheduler models')
class LiveCatalogTests(TransactionTestCase):
    def setUp(self):
        from scheduler.models import Teacher, Classroom
        self.Teacher, self.Classroom = Teacher, Classroom
        self.source = 'https://example.invalid/api/v1'
        self.teacher = Teacher.objects.create(id=10, full_name='Иванов Иван Иванович', short_name='Иванов И.И.')
        self.inactive = Teacher.objects.create(id=11, full_name='Петров Петр Петрович', short_name='Петров П.П.', is_active=False)
        self.classroom = Classroom.objects.create(id=20, title='101', is_active=False)
        self.snapshot('teachers', [dict(id=10, full_name='Старое имя', short_name='Старое И.', endpoint=''),
                                   dict(id=12, full_name='Удаленный преподаватель', short_name='Удаленный П.', endpoint='')])
        self.snapshot('classrooms', [dict(id=21, title='История')])
        self.snapshot('teachers', [dict(id=-1, full_name='Дополнительный преподаватель', short_name='Дополнительный П.', endpoint=None),
                                   dict(id=-2, full_name=self.teacher.full_name, short_name='Иванов И.И.', endpoint=None)],
                      source=SUPPLEMENT_SOURCE)

    def snapshot(self, resource, items, source=None):
        return CatalogSnapshot.objects.create(source=source or self.source, resource=resource,
            fetched_at='2026-01-01T00:00:00+00:00', payload=json.dumps(items, ensure_ascii=False))

    def load(self):
        return load_live_catalogs(source=self.source + '/')

    def test_all_live_rows_and_supplement_without_historical_api_fallback(self):
        historical = list(CatalogSnapshot.objects.values())
        with patch.object(HistoricalCatalogReader, 'load_accumulated_catalog', side_effect=AssertionError('Historical API read')):
            reader = self.load()
        with self.assertNumQueries(0):
            teachers, classrooms = reader.parser_services()
        self.assertEqual({r.id for r in teachers.repo.items}, {10, 11, -1})
        self.assertEqual(teachers.repo.get_by_short_name('Иванов И.И.').full_name, self.teacher.full_name)
        self.assertEqual({r.id for r in classrooms.repo.items}, {20})
        self.assertFalse(teachers.repo.catalog_provenance[11]['is_active'])
        self.assertTrue(teachers.repo.catalog_provenance[11]['present_in_database'])
        self.assertEqual([r['id'] for r in reader.load_catalog(self.source, 'teachers')['items']], [10, 11])
        self.assertEqual(list(CatalogSnapshot.objects.values()), historical)

    def test_memory_is_stable_but_next_load_reads_current_database(self):
        reader = self.load()
        before = reader.load_accumulated_catalog(self.source, 'teachers')
        self.Teacher.objects.filter(pk=10).update(short_name='Измененный И.')
        self.Classroom.objects.filter(pk=20).delete()
        self.Classroom.objects.create(id=22, title='202')
        CatalogExclusionEvent.objects.create(source=self.source, resource='teachers', entity_id=11,
            excluded=True, reviewer='admin', reason='test', recorded_at='2026-10-07T00:00:00+00:00')
        self.snapshot('teachers', [], source=SUPPLEMENT_SOURCE)
        with self.assertNumQueries(0):
            teachers, classrooms = reader.parser_services()
            self.assertEqual(reader.load_accumulated_catalog(self.source, 'teachers'), before)
        self.assertIn(-1, {r.id for r in teachers.repo.items})
        self.assertIn(11, {r.id for r in teachers.repo.items})
        self.assertIn(20, {r.id for r in classrooms.repo.items})
        changed = self.load()
        teachers, classrooms = changed.parser_services()
        self.assertNotIn(11, {r.id for r in teachers.repo.items})
        self.assertIsNotNone(teachers.repo.get_by_short_name('Измененный И.'))
        self.assertNotIn(-1, {r.id for r in teachers.repo.items})
        self.assertEqual({r.id for r in classrooms.repo.items}, {22})

    def test_ambiguity_and_supplement_exclusion(self):
        self.Teacher.objects.create(full_name='Иванов Илья Иванович', short_name='Иванов И.И.')
        CatalogExclusionEvent.objects.create(source=SUPPLEMENT_SOURCE, resource='teachers', entity_id=-1,
            excluded=True, reviewer='admin', reason='test', recorded_at='2026-10-07T00:00:00+00:00')
        teachers, _ = self.load().parser_services()
        self.assertIsNone(teachers.repo.get_by_short_name('Иванов И.И.'))
        self.assertNotIn(-1, {r.id for r in teachers.repo.items})

    def test_invalid_input_and_empty_database_do_not_fall_back_to_history(self):
        self.Classroom.objects.filter(pk=20).update(title='')
        with self.assertRaisesRegex(ValueError, 'display name'):
            self.load()
        self.Classroom.objects.all().delete()
        with self.assertRaisesRegex(ValueError, 'Empty catalog'):
            self.load()
        with self.assertRaisesRegex(ValueError, 'explicit'):
            load_live_catalogs(source=' ')
        with transaction.atomic():
            with self.assertRaisesRegex(ValueError, 'existing transaction'):
                self.load()

    def test_loading_is_read_only_and_returned_values_are_detached(self):
        def readonly(execute, sql, params, many, context):
            if sql.lstrip().split()[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'REPLACE'}:
                raise AssertionError('Catalog load must not write')
            return execute(sql, params, many, context)
        with connection.execute_wrapper(readonly):
            reader = self.load()
        changed = reader.load_accumulated_catalog(self.source, 'teachers')
        changed['items'].clear()
        self.assertTrue(reader.load_accumulated_catalog(self.source, 'teachers')['items'])

    @skipUnless(connection.vendor == 'postgresql', 'PostgreSQL MVCC test')
    def test_concurrent_catalog_edit_is_visible_only_to_next_load(self):
        import psycopg2
        original = HistoricalCatalogReader.catalog_exclusions
        def read(history, source, resource):
            if source == self.source and resource == 'teachers':
                other = psycopg2.connect(**connection.get_connection_params())
                try:
                    with other, other.cursor() as cursor:
                        cursor.execute('UPDATE scheduler_classroom SET title = %s WHERE id = %s', ('202', 20))
                finally:
                    other.close()
            return original(history, source, resource)
        with patch.object(HistoricalCatalogReader, 'catalog_exclusions', read):
            reader = self.load()
        _, classrooms = reader.parser_services()
        self.assertIsNotNone(classrooms.repo.get_by_title('101'))
        _, classrooms = self.load().parser_services()
        self.assertIsNotNone(classrooms.repo.get_by_title('202'))
