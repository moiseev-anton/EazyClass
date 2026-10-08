import os
import subprocess
import sys
import tempfile
import time
import uuid
from unittest import skipUnless

from celery import Celery
from django.db import connection
from django.test import TransactionTestCase
from redis import Redis

from schedule_ingestion.models import PublicationDelivery
from schedule_ingestion.tests import test_delivery_recovery as fixtures


@skipUnless(os.name == 'posix' and os.environ.get('TABLEPARSER_TEST_REDIS_PORT'),
            'Requires Linux and disposable Redis')
class WorkerCrashTests(TransactionTestCase):
    setUp = fixtures.RecoveryTests.setUp
    version = fixtures.RecoveryTests.version
    lesson = fixtures.RecoveryTests.lesson
    prepare = fixtures.RecoveryTests.prepare
    apply = fixtures.RecoveryTests.apply
    resolve = fixtures.RecoveryTests.resolve

    def test_killed_sender_is_not_resent_and_operator_can_resume_report(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_tableparser_validation')
        self.assertEqual(connection.settings_dict['HOST'], '127.0.0.1')
        publication = self.apply(self.prepare(self.version()))
        port = int(os.environ['TABLEPARSER_TEST_REDIS_PORT'])
        prefix = 'crash-test:' + str(uuid.uuid4())
        redis = Redis(host='127.0.0.1', port=port, db=2)
        self.addCleanup(redis.close)
        app = Celery('crash_test_client', fixups=[], set_as_current=False,
            broker=f'redis://127.0.0.1:{port}/0', backend=f'redis://127.0.0.1:{port}/1')
        self.addCleanup(app.close)
        log = tempfile.TemporaryFile(mode='w+b')
        self.addCleanup(log.close)

        def stop(process):
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)

        def start(block):
            env = dict(os.environ, TABLEPARSER_CRASH_TEST='1', TABLEPARSER_CRASH_PREFIX=prefix,
                       TABLEPARSER_CRASH_BLOCK='1' if block else '0')
            process = subprocess.Popen([sys.executable, '-B', '-m', 'celery',
                '-A', 'schedule_ingestion.tests.crash_worker:app', 'worker', '--pool=solo',
                '--concurrency=1', '--queues=periodic_tasks', '--loglevel=ERROR',
                '--without-gossip', '--without-mingle', '--without-heartbeat'],
                env=env, stdout=log, stderr=subprocess.STDOUT)
            self.addCleanup(stop, process)
            return process

        first = start(True)
        app.send_task('schedule_ingestion.tasks.notify_publication', args=[str(publication.pk)],
                      queue='periodic_tasks')
        deadline = time.monotonic() + 40
        while not redis.get(prefix + ':notifications'):
            if first.poll() is not None or time.monotonic() >= deadline:
                log.seek(0)
                self.fail('Worker did not reach sender: ' + log.read().decode(errors='replace'))
            time.sleep(0.1)
        stop(first)  # SIGKILL: no finally block or status update can run.
        delivery = PublicationDelivery.objects.get(publication=publication, phase='notifications')
        self.assertEqual(delivery.status, 'sending')
        second = start(False)
        replay = app.send_task('schedule_ingestion.tasks.notify_publication',
            args=[str(publication.pk)], queue='periodic_tasks')
        self.assertEqual(type(replay.get(timeout=40, propagate=False)).__name__, 'DeliveryUncertain')
        self.assertEqual(redis.get(prefix + ':notifications'), b'1')
        self.resolve(publication, delivery, decision='skip', worker_stopped=True,
                     reason='Killed worker after simulated send; do not duplicate')
        report = app.send_task('schedule_ingestion.tasks.report_publication',
            args=[str(publication.pk)], queue='periodic_tasks')
        self.assertEqual(report.get(timeout=40), str(publication.pk))
        self.assertEqual(redis.get(prefix + ':notifications'), b'1')
        self.assertEqual(redis.get(prefix + ':report'), b'1')
        self.assertEqual(publication.deliveries.get(phase='report').status, 'completed')
        stop(second)
