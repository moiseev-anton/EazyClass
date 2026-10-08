import importlib.metadata
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from schedule_ingestion.parser_runtime import runtime_manifest
from schedule_ingestion.release_bundle import verify_bundle


class Command(BaseCommand):
    help = 'Read-only release readiness check: files, installed packages, schema and optional imported knowledge.'

    def add_arguments(self, parser):
        parser.add_argument('manifest', type=Path)
        parser.add_argument('--expected-sha256', required=True)
        parser.add_argument('--require-imported', action='store_true')

    def handle(self, *args, **options):
        try:
            manifest = options['manifest'].resolve(strict=True)
            bundle = verify_bundle(manifest, options['expected_sha256'])
            profile = getattr(settings, 'TABLEPARSER_RUNTIME', None)
            if not profile or Path(profile['resource_root']).resolve() != manifest.parent / 'runtime':
                raise ValueError('TABLEPARSER_RUNTIME must point to this release runtime directory')
            runtime = runtime_manifest(**dict(root=profile['resource_root'], catalog_source=profile['catalog_source']))
            expected_resources = {name.removeprefix('runtime/'): sha for name, sha in bundle['files'].items()
                                  if name.startswith('runtime/')}
            if runtime['code'] != bundle['code'] or runtime['resources'] != expected_resources:
                raise ValueError('Installed code or runtime resources differ from the release')
            for name, version in bundle['dependencies'].items():
                if importlib.metadata.version(name) != version:
                    raise ValueError('Installed dependency differs: ' + name)
            if connection.vendor != 'postgresql':
                raise ValueError('Server readiness requires PostgreSQL')
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes('schedule_ingestion')
            if executor.migration_plan(targets):
                raise ValueError('Ingestion migrations have not been applied')
            if options['require_imported']:
                from schedule_ingestion.knowledge_import import read_snapshot, verify_imported
                verify_imported(read_snapshot(manifest.parent / bundle['knowledge']))
        except (ValueError, OSError, KeyError, importlib.metadata.PackageNotFoundError) as error:
            raise CommandError(str(error)) from error
        self.stdout.write(json.dumps(dict(status='ready', parser_version=bundle['parser_version'],
            manifest_sha256=options['expected_sha256'], knowledge_verified=options['require_imported'])))
