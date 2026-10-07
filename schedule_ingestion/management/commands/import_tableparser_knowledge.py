import json
import sqlite3
from django.core.management.base import BaseCommand, CommandError
from schedule_ingestion.knowledge_import import read_snapshot, import_snapshot


class Command(BaseCommand):
    help = 'Validate TableParser knowledge SQLite v3; --apply performs initial atomic import.'

    def add_arguments(self, parser):
        parser.add_argument('source')
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        try:
            snapshot = read_snapshot(options['source'])
            result = (import_snapshot(snapshot, using=options['database']) if options['apply'] else
                      dict(status='validated', sha256=snapshot.sha256, counts=snapshot.counts))
        except (OSError, ValueError, sqlite3.Error) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True))
