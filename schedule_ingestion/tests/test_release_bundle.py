import io
import json
from pathlib import Path
import tempfile
from unittest.mock import patch, MagicMock
import zipfile

from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings

from eazyclass.tableparser_settings import runtime_profile
from schedule_ingestion.release_bundle import build_bundle, inventory, sha256, verify_bundle


class ReleaseBundleTests(SimpleTestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.resources = self.root / 'resources'
        (self.resources / 'config').mkdir(parents=True)
        (self.resources / 'config/rules.json').write_text('{}')
        (self.resources / 'data').mkdir()
        (self.resources / 'data/knowledge.sqlite3').write_bytes(b'unused local knowledge')
        self.seed = self.root / 'seed.sqlite3'
        self.seed.write_bytes(b'explicit seed')
        self.wheel = self.root / 'parser.whl'
        with zipfile.ZipFile(self.wheel, 'w') as archive:
            archive.writestr('tableparser_api.py', 'VERSION = 1\n')
        self.report = self.root / 'install.json'
        self.report.write_text(json.dumps({'environment': {'python_version': '3.12'}, 'install': [
            {'metadata': {'name': 'eazyclass-tableparser', 'version': '0.1.1'},
             'download_info': {'archive_info': {'hashes': {'sha256': sha256(self.wheel)}}}},
            {'metadata': {'name': 'Django', 'version': '5.2.7'}},
        ]}))
        self.output = self.root / 'release'

    def build(self):
        return build_bundle(wheel=self.wheel, wheel_sha256=sha256(self.wheel),
                            resources=self.resources, knowledge=self.seed,
                            install_report=self.report, output=self.output)

    def test_explicit_seed_is_separate_and_original_resources_stay_unchanged(self):
        before = inventory(self.resources)
        checksum = self.build()
        bundle = verify_bundle(self.output / 'release.json', checksum)
        self.assertEqual(inventory(self.resources), before)
        self.assertFalse((self.output / 'runtime/data/knowledge.sqlite3').exists())
        self.assertEqual((self.output / bundle['knowledge']).read_bytes(), self.seed.read_bytes())
        self.assertEqual(bundle['excluded_resource_knowledge_sha256'], before['data/knowledge.sqlite3'])
        self.assertEqual(bundle['dependencies']['django'], '5.2.7')
        for name in ('Dockerfile', 'constraints.txt', 'wheel.sha256'):
            self.assertNotIn(b'\r', (self.output / 'image' / name).read_bytes())
        with self.assertRaisesRegex(ValueError, 'never overwrite'):
            self.build()

    def test_modified_missing_and_extra_files_are_rejected(self):
        checksum = self.build()
        target = self.output / 'runtime/config/rules.json'
        original = target.read_bytes()
        for action in ('modify', 'missing', 'extra'):
            with self.subTest(action=action):
                if action == 'modify':
                    target.write_bytes(b'changed')
                elif action == 'missing':
                    target.unlink()
                else:
                    (self.output / 'unexpected').write_text('x')
                with self.assertRaisesRegex(ValueError, 'inventory differs'):
                    verify_bundle(self.output / 'release.json', checksum)
                target.write_bytes(original)
        with self.assertRaisesRegex(ValueError, 'manifest checksum'):
            verify_bundle(self.output / 'release.json', '0' * 64)

    def test_unapproved_wheel_fails_before_creating_output(self):
        with self.wheel.open('ab') as stream:
            stream.write(b'changed')
        with self.assertRaisesRegex(ValueError, 'another wheel'):
            self.build()
        self.assertFalse(self.output.exists())

    def test_readiness_rejects_unconfigured_runtime(self):
        checksum = self.build()
        with override_settings(TABLEPARSER_RUNTIME=None), self.assertRaisesRegex(CommandError, 'must point'):
            call_command('check_tableparser_release', str(self.output / 'release.json'), expected_sha256=checksum)

    def test_readiness_rejects_pending_migrations_then_verifies_import(self):
        checksum = self.build()
        bundle = verify_bundle(self.output / 'release.json', checksum)
        module = 'schedule_ingestion.management.commands.check_tableparser_release'
        runtime = {'code': bundle['code'], 'resources': {'config/rules.json': sha256(self.resources / 'config/rules.json')}}
        connection = MagicMock(vendor='postgresql')
        executor = MagicMock()
        executor.migration_plan.return_value = ['pending']
        with override_settings(TABLEPARSER_RUNTIME={'resource_root': str(self.output / 'runtime'), 'catalog_source': 'api'}), \
                patch(module + '.runtime_manifest', return_value=runtime), \
                patch(module + '.importlib.metadata.version', side_effect=bundle['dependencies'].__getitem__), \
                patch(module + '.connection', connection), \
                patch(module + '.MigrationExecutor', return_value=executor), \
                patch('schedule_ingestion.knowledge_import.read_snapshot') as read, \
                patch('schedule_ingestion.knowledge_import.verify_imported') as verify:
            with self.assertRaisesRegex(CommandError, 'migrations have not'):
                call_command('check_tableparser_release', str(self.output / 'release.json'), expected_sha256=checksum)
            verify.assert_not_called()
            executor.migration_plan.return_value = []
            output = io.StringIO()
            call_command('check_tableparser_release', str(self.output / 'release.json'),
                         expected_sha256=checksum, require_imported=True, stdout=output)
            verify.assert_called_once_with(read.return_value)
            self.assertTrue(json.loads(output.getvalue())['knowledge_verified'])


class RuntimeProfileTests(SimpleTestCase):
    def test_disabled_until_both_values_are_configured(self):
        self.assertIsNone(runtime_profile({}))
        for environ in ({'TABLEPARSER_RESOURCE_ROOT': str(Path.cwd())},
                        {'TABLEPARSER_CATALOG_SOURCE': 'api'},
                        {'TABLEPARSER_RESOURCE_ROOT': 'relative', 'TABLEPARSER_CATALOG_SOURCE': 'api'}):
            with self.assertRaises(ImproperlyConfigured):
                runtime_profile(environ)
        result = runtime_profile({'TABLEPARSER_RESOURCE_ROOT': str(Path.cwd()), 'TABLEPARSER_CATALOG_SOURCE': ' api/ '})
        self.assertEqual(result['catalog_source'], 'api')
