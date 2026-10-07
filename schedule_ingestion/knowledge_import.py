"""One-time, lossless import of TableParser schema v3 into Django storage."""
import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from django.core.management.color import no_style
from django.db import connections, transaction
from django.utils import timezone

from . import models


TABLES = {
    'catalog_snapshots': (models.CatalogSnapshot, 'id source resource fetched_at payload'),
    'sync_failures': (models.CatalogSyncFailure, 'id source resource attempted_at error_type'),
    'archive_files': (models.ArchiveFile, 'id path sha256 imported_at'),
    'observations': (models.Observation, 'id file_id raw_cell context output archive_records record_numbers label_status'),
    'aliases': (models.Alias, 'id kind spelling target source'),
    'confirmed_corrections': (models.Confirmation, 'id raw_cell context output reviewer evidence confirmed_at'),
    'correction_revocations': (models.ConfirmationRevocation, 'correction_id reviewer reason revoked_at'),
    'catalog_exclusion_events': (models.CatalogExclusionEvent, 'id source resource entity_id excluded reviewer reason recorded_at'),
}
JSON_TYPES = {'context': dict, 'output': list, 'payload': list, 'archive_records': list, 'record_numbers': list}
DATES = {'fetched_at', 'attempted_at', 'imported_at', 'confirmed_at', 'revoked_at', 'recorded_at'}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def raw_hash(raw):
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


@dataclass
class KnowledgeSnapshot:
    source_path: str
    sha256: str
    tables: dict

    @property
    def counts(self):
        return {name: len(rows) for name, rows in self.tables.items()}


def read_snapshot(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('SQLite source does not exist')
    # SQLite backup sees a consistent snapshot including committed WAL pages.
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as source:
        with closing(sqlite3.connect(':memory:')) as db:
            source.backup(db)
            db.row_factory = sqlite3.Row
            if db.execute('PRAGMA user_version').fetchone()[0] != 3:
                raise ValueError('Only TableParser knowledge schema v3 is supported')
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('SQLite integrity check failed')
            if db.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('Broken source foreign keys')
            present = {r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            if present != set(TABLES):
                raise ValueError('Unexpected SQLite tables')
            tables = {}
            for name, (_, column_text) in TABLES.items():
                columns = column_text.split()
                source_columns = columns[1:] if name == 'aliases' else columns
                actual = [r['name'] for r in db.execute(f'PRAGMA table_info("{name}")')]
                if actual != source_columns:
                    raise ValueError('Unexpected columns: ' + name)
                query = f'SELECT {"rowid AS id, *" if name == "aliases" else "*"} FROM "{name}" ORDER BY 1'
                rows = [dict(row) for row in db.execute(query)]
                for row in rows:
                    for key, value in row.items():
                        if key in ('id', 'correction_id', 'file_id', 'entity_id', 'excluded'):
                            if type(value) is not int:
                                raise ValueError('Invalid integer: ' + name + '.' + key)
                            if key == 'excluded' and value not in (0, 1):
                                raise ValueError('Invalid exclusion flag')
                        elif not isinstance(value, str):
                            raise ValueError('Invalid text: ' + name + '.' + key)
                        if key in JSON_TYPES and not isinstance(json.loads(value), JSON_TYPES[key]):
                            raise ValueError('Invalid JSON structure: ' + name + '.' + key)
                        if key in DATES and datetime.fromisoformat(value).utcoffset() is None:
                            raise ValueError('Timestamp must include timezone: ' + name + '.' + key)
                    if name == 'observations' and row['label_status'] != 'unreviewed':
                        raise ValueError('An observation must remain unreviewed')
                tables[name] = rows
    files = {r['id'] for r in tables['archive_files']}
    corrections = {r['id'] for r in tables['confirmed_corrections']}
    if any(r['file_id'] not in files for r in tables['observations']):
        raise ValueError('Observation references a missing archive')
    if any(r['correction_id'] not in corrections for r in tables['correction_revocations']):
        raise ValueError('Revocation references a missing confirmation')
    return KnowledgeSnapshot(str(path), fingerprint(tables), tables)


def model_values(name, row):
    values = dict(row)
    identity = {
        'archive_files': ('path', 'sha256'),
        'aliases': ('kind', 'spelling', 'target', 'source'),
        'confirmed_corrections': ('raw_cell', 'context', 'output', 'reviewer', 'evidence'),
    }.get(name)
    if identity:
        values['identity_sha256'] = fingerprint([row[key] for key in identity])
    if name == 'confirmed_corrections':
        values['raw_cell_sha256'] = raw_hash(row['raw_cell'])
    return values


def verify_imported(snapshot, using='default'):
    """Original rows must match; subsequent new knowledge may coexist."""
    for name, (model, columns) in TABLES.items():
        rows = snapshot.tables[name]
        key = columns.split()[0]
        for start in range(0, len(rows), 500):
            batch = rows[start:start + 500]
            expected = {row[key]: model_values(name, row) for row in batch}
            fields = list(next(iter(expected.values()))) if expected else []
            actual = {row[key]: row for row in model.objects.using(using).filter(
                **{key + '__in': list(expected)}).values(*fields)}
            if actual != expected:
                raise ValueError('Imported data differs: ' + name)


def import_snapshot(snapshot, *, using='default'):
    with transaction.atomic(using=using):
        models.KnowledgeImport.objects.using(using).get_or_create(pk=1)
        ledger = models.KnowledgeImport.objects.using(using).select_for_update().get(pk=1)
        if ledger.source_sha256:
            if ledger.source_sha256 != snapshot.sha256:
                raise ValueError('A different knowledge snapshot was already imported')
            verify_imported(snapshot, using)
            return dict(status='already_imported', sha256=snapshot.sha256, counts=snapshot.counts)
        if any(model.objects.using(using).exists() for model, _ in TABLES.values()):
            raise ValueError('Knowledge storage must be empty before initial import')
        for name, (model, _) in TABLES.items():
            rows = snapshot.tables[name]
            for start in range(0, len(rows), 500):
                model.objects.using(using).bulk_create(
                    [model(**model_values(name, row)) for row in rows[start:start + 500]], batch_size=500)
        # Explicit imported IDs must not collide with subsequent server inserts.
        connection = connections[using]
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), [model for model, _ in TABLES.values()]):
                cursor.execute(sql)
        verify_imported(snapshot, using)
        ledger.source_sha256 = snapshot.sha256
        ledger.source_path = snapshot.source_path
        ledger.counts = snapshot.counts
        ledger.imported_at = timezone.now()
        ledger.save(using=using)
    return dict(status='imported', sha256=snapshot.sha256, counts=snapshot.counts)
