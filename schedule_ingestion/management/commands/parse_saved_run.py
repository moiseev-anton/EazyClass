from django.core.management.base import BaseCommand

from schedule_ingestion.parse_execution import execute_parse


class Command(BaseCommand):
    help = 'Parse one stored run into an export revision; does not publish a schedule.'

    def add_arguments(self, parser):
        parser.add_argument('run_id')
        parser.add_argument('--resources', required=True)
        parser.add_argument('--catalog-source', required=True)
        parser.add_argument('--database', default='default')

    def handle(self, *args, **options):
        revision = execute_parse(options['run_id'], resource_root=options['resources'],
            catalog_source=options['catalog_source'], using=options['database'])
        self.stdout.write(str(revision.pk))
