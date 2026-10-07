"""Opt-in full parser parity against disposable PostgreSQL; no live settings."""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import os
import sqlite3
import sys
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def normalize(value, root):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key == 'model_directory' and isinstance(item, str):
                path = Path(item).resolve()
                if not path.is_relative_to(root):
                    raise ValueError('Model outside resources')
                result[key] = '<runtime>/' + path.relative_to(root).as_posix()
            else:
                result[key] = normalize(item, root)
        return result
    if isinstance(value, list):
        return [normalize(item, root) for item in value]
    return value


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'state', 'baseline', 'output'):
        cli.add_argument('--' + name, type=Path, required=True)
    args = cli.parse_args()
    source, state, baseline, output = [getattr(args, key).resolve() for key in ('source','state','baseline','output')]
    if output.exists() or output.is_relative_to(state) or output.is_relative_to(baseline):
        raise ValueError('Use a new independent output directory')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'schedule_ingestion.tests.postgres_settings'
    import django
    django.setup()
    from django.db import connection
    if connection.vendor != 'postgresql':
        raise ValueError('PostgreSQL is required')
    from schedule_ingestion.knowledge_import import read_snapshot, verify_imported
    from schedule_ingestion.knowledge_reader import DjangoKnowledgeReader
    from schedule_ingestion.historical_catalogs import HistoricalCatalogReader
    from eazyclass_tableparser import RawTable, RuntimeResources, create_context, parse_tables
    from knowledge_store import KnowledgeStore
    from sqlite_knowledge_reader import SQLiteKnowledgeReader
    from repositories import TeacherRepository, ClassroomRepository
    from services import TeacherService, ClassroomService
    from config.loader import load_yaml
    from schedule_csv import write_schedule_file

    class SourceStore(KnowledgeStore):
        def __init__(self, path): self.path = path
        @contextmanager
        def connect(self):
            with closing(sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True)) as db:
                db.row_factory = sqlite3.Row
                yield db

    before = digest(source)
    snapshot = read_snapshot(source)
    verify_imported(snapshot)
    completed = json.loads((baseline / 'completed.json').read_text(encoding='utf-8'))
    for name in ('manifest', 'report'):
        if digest(baseline / (name + '.json')) != completed[name + '_sha256']:
            raise ValueError('Baseline metadata differs')
    if completed['status'] != 'equal': raise ValueError('Baseline is not equivalent')
    manifest = json.loads((baseline / 'manifest.json').read_text(encoding='utf-8'))
    expected_cases = json.loads((baseline / 'report.json').read_text(encoding='utf-8'))['cases']
    resources = RuntimeResources.from_root(state)
    state_hashes = {}
    for name, entry in manifest['runtime_files'].items():
        if entry['role'] != 'code':
            state_hashes[name] = entry['sha256']
            if digest(state / name) != entry['sha256']: raise ValueError('Resource differs: ' + name)
    source_store = SourceStore(source)
    sqlite_reader = SQLiteKnowledgeReader(source_store)
    pg_reader = DjangoKnowledgeReader()
    as_of = datetime.fromisoformat(manifest['spec']['as_of'])
    swaps = load_yaml(resources.swaps_file, default={})
    assert sqlite_reader.subject_names() == pg_reader.subject_names()
    assert sqlite_reader.teacher_records() == pg_reader.teacher_records()
    left, right = sqlite_reader.subject_index(swaps), pg_reader.subject_index(swaps)
    assert left.entries == right.entries and left.aliases == right.aliases
    for instant in (datetime(1900,1,1,tzinfo=timezone.utc), as_of, datetime(2100,1,1,tzinfo=timezone.utc)):
        assert sqlite_reader.verified_records(as_of=instant) == pg_reader.verified_records(as_of=instant)
        assert sqlite_reader.subject_feedback(as_of=instant) == pg_reader.subject_feedback(as_of=instant)
    for row in snapshot.tables['confirmed_corrections']:
        context = json.loads(row['context'])
        for query in (context, dict(context, date='2099-01-01')):
            for name in ('lookup_applicable', 'repeated_confirmation'):
                assert getattr(sqlite_reader,name)(row['raw_cell'],query) == getattr(pg_reader,name)(row['raw_cell'],query), name
    catalogs = HistoricalCatalogReader()
    for source_name, resource in {(r['source'],r['resource']) for r in snapshot.tables['catalog_snapshots']}:
        for method in ('load_catalog','load_accumulated_catalog','catalog_exclusions'):
            assert getattr(source_store,method)(source_name,resource) == getattr(catalogs,method)(source_name,resource), method

    services = {}
    for repo_type, service_type, key in ((TeacherRepository,TeacherService,'teacher_service'),
                                        (ClassroomRepository,ClassroomService,'classroom_service')):
        repo = repo_type(store=catalogs, source=manifest['spec']['catalog_source'])
        assert repo.load_local(), key
        services[key] = service_type(repo)
    ctx = create_context(knowledge=pg_reader, resources=resources, as_of=as_of, **services)
    output.mkdir(parents=True)
    (output/'INCOMPLETE.json').write_text('{}',encoding='utf-8')
    implementation = {p.name: digest(p) for p in Path(__file__).resolve().parents[1].glob('*.py')}
    import psycopg2
    report = dict(postgres_driver_version=psycopg2.__version__, status='running', backend=connection.vendor, counts=snapshot.counts,
                  source_logical_sha256=snapshot.sha256, source_file_sha256=before,
                  reader_contract_equal=True, historical_catalogs_equal=True, cases=[],
                  implementation=implementation,
                  versions={name: importlib.metadata.version(name) for name in ('Django','numpy','scikit-learn','jsonapi-client')})

    def no_sqlite(event, args):
        if event == 'sqlite3.connect': raise RuntimeError('SQLite access forbidden during PostgreSQL parsing')
    sys.addaudithook(no_sqlite)
    # PostgreSQL connections remain allowed; only the parser's SQLite path is blocked.
    fields = ('parser_output','final_output','review_queue','groups','csv_rows','sidecar')
    for case in expected_cases:
        stamp = case['snapshot']
        work = output/stamp
        work.mkdir()
        tables = []
        for relative, sha in manifest['snapshots'][stamp].items():
            path = baseline/stamp/'source'/relative
            if digest(path) != sha: raise ValueError('Input differs')
            pieces = path.stem.split('_',3)
            with path.open(encoding='utf-8-sig',newline='') as stream:
                rows = list(csv.reader(stream))
            tables.append(RawTable(pieces[3].replace('_',' '),rows,datetime.fromisoformat(pieces[1]).date()))
        print('PostgreSQL parse:', stamp, flush=True)
        result = parse_tables(tables,ctx)
        csv_path = work/'schedule.csv'
        write_schedule_file(csv_path,result.lessons)
        with csv_path.open(encoding='utf-8-sig',newline='') as stream:
            csv_rows = list(csv.DictReader(stream))
        actual = normalize(dict(parser_output=result.parser_lessons,final_output=result.lessons,
            review_queue=sorted(result.review_items,key=lambda item:item['id']), groups=result.groups,
            csv_rows=csv_rows,sidecar=json.loads(Path(str(csv_path)+'.review.json').read_text(encoding='utf-8'))),state)
        expected_path = baseline/stamp/'source/result.json'
        if digest(expected_path) != case['source_sha256']: raise ValueError('Expected result differs')
        expected = json.loads(expected_path.read_text(encoding='utf-8'))
        different = [key for key in fields if canonical(actual[key]) != canonical(expected[key])]
        (work/'result.json').write_text(json.dumps(actual,ensure_ascii=False,sort_keys=True,indent=2),encoding='utf-8')
        report['cases'].append(dict(snapshot=stamp,lessons=len(result.lessons),equal=not different,
                                   different_fields=different,result_sha256=digest(work/'result.json')))
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        if different: raise ValueError('PostgreSQL results differ: '+str(different))
        print('Compared: equal',flush=True)
    verify_imported(snapshot)
    assert digest(source) == before
    assert all(digest(state/name)==sha for name,sha in state_hashes.items())
    report.update(status='equal', knowledge_unchanged=True, sqlite_blocked_during_parse=True)
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'completed.json').write_text(json.dumps(dict(status='equal',report_sha256=digest(output/'report.json'))),encoding='utf-8')
    (output/'INCOMPLETE.json').unlink()


if __name__ == '__main__':
    main()
