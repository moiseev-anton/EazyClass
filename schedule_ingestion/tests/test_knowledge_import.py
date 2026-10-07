import hashlib
import io
import json
import sqlite3
from contextlib import closing
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from schedule_ingestion import models
from schedule_ingestion.knowledge_import import TABLES, import_snapshot, read_snapshot, verify_imported, model_values
from schedule_ingestion.knowledge_reader import DjangoKnowledgeReader


def make_source(path):
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
            PRAGMA user_version=3;
            CREATE TABLE catalog_snapshots(id INTEGER PRIMARY KEY,source TEXT,resource TEXT,fetched_at TEXT,payload TEXT);
            CREATE TABLE sync_failures(id INTEGER PRIMARY KEY,source TEXT,resource TEXT,attempted_at TEXT,error_type TEXT);
            CREATE TABLE archive_files(id INTEGER PRIMARY KEY,path TEXT,sha256 TEXT,imported_at TEXT);
            CREATE TABLE observations(id INTEGER PRIMARY KEY,file_id INTEGER,raw_cell TEXT,context TEXT,output TEXT,archive_records TEXT,record_numbers TEXT,label_status TEXT);
            CREATE TABLE aliases(kind TEXT,spelling TEXT,target TEXT,source TEXT);
            CREATE TABLE confirmed_corrections(id INTEGER PRIMARY KEY,raw_cell TEXT,context TEXT,output TEXT,reviewer TEXT,evidence TEXT,confirmed_at TEXT);
            CREATE TABLE correction_revocations(correction_id INTEGER PRIMARY KEY,reviewer TEXT,reason TEXT,revoked_at TEXT);
            CREATE TABLE catalog_exclusion_events(id INTEGER PRIMARY KEY,source TEXT,resource TEXT,entity_id INTEGER,excluded INTEGER,reviewer TEXT,reason TEXT,recorded_at TEXT);
        ''')
        when = '2026-01-01T10:11:12.123456+03:00'
        context = '{"sheet_name": "Лист", "group": "А"}'
        output = '[{"subject": "Физика", "teacher": "Иванов И.И.", "classroom": null, "part": 0, "subgroup": 0}]'
        db.execute('INSERT INTO catalog_snapshots VALUES(3,?,?,?,?)', ('api', 'teachers', when, '[{"id": 10}]'))
        db.execute('INSERT INTO sync_failures VALUES(4,?,?,?,?)', ('api', 'teachers', when, 'Timeout'))
        db.execute('INSERT INTO archive_files VALUES(7,?,?,?)', ('archive/file.csv', 'a'*64, when))
        db.execute('INSERT INTO observations VALUES(11,7,?,?,?,?,?,?)', ('raw',context,output,'[{"row": 1}]','[2]','unreviewed'))
        db.execute('INSERT INTO aliases(rowid,kind,spelling,target,source) VALUES(23,?,?,?,?)', ('teacher','name','canonical','archive'))
        db.execute('INSERT INTO confirmed_corrections VALUES(19,?,?,?,?,?,?)', ('raw',context,output,'reviewer','evidence',when))
        db.execute('INSERT INTO correction_revocations VALUES(19,?,?,?)', ('reviewer','revoked','2026-12-01T00:00:00+00:00'))
        db.execute('INSERT INTO catalog_exclusion_events VALUES(29,?,?,?,?,?,?,?)', ('api','teachers',10,1,'reviewer','reason',when))


class KnowledgeImportTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'knowledge.sqlite3'
        make_source(self.path)

    def test_preserves_every_field_ids_and_source_then_repeats_without_overwrite(self):
        original = hashlib.sha256(self.path.read_bytes()).hexdigest()
        snapshot = read_snapshot(self.path)
        self.assertEqual(import_snapshot(snapshot)['status'], 'imported')
        verify_imported(snapshot)
        self.assertEqual(models.Observation.objects.get().file_id, 7)
        self.assertEqual(models.Alias.objects.get().pk, 23)
        self.assertEqual(models.ConfirmationRevocation.objects.get().pk, 19)
        self.assertEqual(models.Confirmation.objects.get().confirmed_at, '2026-01-01T10:11:12.123456+03:00')
        self.assertEqual(models.Observation.objects.get().label_status, 'unreviewed')
        extra = models.CatalogSyncFailure.objects.create(source='new',resource='teachers',attempted_at='2026-01-02T00:00:00+00:00',error_type='Other')
        self.assertGreater(extra.pk, 4)
        self.assertEqual(import_snapshot(snapshot)['status'], 'already_imported')
        self.assertTrue(models.CatalogSyncFailure.objects.filter(pk=extra.pk).exists())
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), original)

    def test_failure_rolls_back_all_tables_and_ledger(self):
        snapshot = read_snapshot(self.path)
        with patch('schedule_ingestion.knowledge_import.verify_imported', side_effect=ValueError('verification failed')):
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                import_snapshot(snapshot)
        self.assertFalse(models.KnowledgeImport.objects.exists())
        self.assertTrue(all(not model.objects.exists() for model, _ in TABLES.values()))

    def test_different_source_or_changed_imported_row_is_rejected(self):
        snapshot = read_snapshot(self.path)
        import_snapshot(snapshot)
        models.Confirmation.objects.filter(pk=19).update(evidence='changed')
        with self.assertRaisesRegex(ValueError, 'Imported data differs'):
            import_snapshot(snapshot)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE confirmed_corrections SET evidence='different source'")
        with self.assertRaisesRegex(ValueError, 'different knowledge snapshot'):
            import_snapshot(read_snapshot(self.path))

    def test_nonempty_destination_is_not_overwritten(self):
        models.CatalogSyncFailure.objects.create(source='existing',resource='teachers',attempted_at='2026-01-01T00:00:00+00:00',error_type='Error')
        with self.assertRaisesRegex(ValueError, 'must be empty'):
            import_snapshot(read_snapshot(self.path))
        self.assertEqual(models.CatalogSyncFailure.objects.count(), 1)
        self.assertFalse(models.KnowledgeImport.objects.exists())

    def test_preview_does_not_access_destination(self):
        output = io.StringIO()
        with self.assertNumQueries(0):
            call_command('import_tableparser_knowledge', str(self.path), stdout=output)
        self.assertEqual(json.loads(output.getvalue())['status'], 'validated')

    def test_invalid_version_broken_reference_or_bad_json_rejected(self):
        for sql in ['PRAGMA user_version=4', 'UPDATE observations SET file_id=999',
                    "UPDATE observations SET output='{}'", "UPDATE archive_files SET imported_at='2026-01-01T00:00:00'"]:
            with self.subTest(sql=sql):
                with closing(sqlite3.connect(self.path)) as db, db:
                    db.execute(sql)
                with self.assertRaises(ValueError):
                    read_snapshot(self.path)
                # Recreate only this explicitly owned temporary fixture.
                self.path.unlink()
                make_source(self.path)

    def test_reader_keeps_existing_future_revocation_policy(self):
        from datetime import datetime, timezone
        import_snapshot(read_snapshot(self.path))
        reader = DjangoKnowledgeReader()
        now = datetime(2026,10,7,tzinfo=timezone.utc)
        self.assertEqual(reader.lookup_applicable('raw', {'sheet_name':'Лист','group':'А'})['status'], 'missing')
        self.assertIsNone(reader.repeated_confirmation('raw', {'sheet_name':'Лист','group':'А'}))
        self.assertEqual(reader.verified_records(as_of=now), [])
        history = reader.teacher_records()
        self.assertEqual(history[0]['id'], 19)
        self.assertEqual(history[0]['revoked_at'], '2026-12-01T00:00:00+00:00')
