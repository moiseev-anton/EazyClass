"""Test-only worker: records simulated sends in disposable Redis, never contacts users."""
import os
from types import SimpleNamespace

if os.environ.get('TABLEPARSER_CRASH_TEST') != '1':
    raise RuntimeError('This worker requires explicit crash-test opt-in')
os.environ['DJANGO_SETTINGS_MODULE'] = 'schedule_ingestion.tests.crash_worker_settings'

import django
django.setup()
from celery import Celery
from redis import Redis
from scheduler.tasks import notification

port = int(os.environ['TABLEPARSER_TEST_REDIS_PORT'])
prefix = os.environ['TABLEPARSER_CRASH_PREFIX']
redis = Redis(host='127.0.0.1', port=port, db=2)


def notify(summary):
    redis.incr(prefix + ':notifications')
    if os.environ.get('TABLEPARSER_CRASH_BLOCK') == '1':
        # Parent kills this worker after the simulated external side effect.
        redis.blpop(prefix + ':never-released', timeout=60)
        raise RuntimeError('Crash test failed to terminate blocked worker')
    return dict(summary, notification_summary={'type': 'NotificationSummary',
        'success_count': 1, 'failed_count': 0, 'blocked_chat_ids': []})


def report(summary):
    redis.incr(prefix + ':report')
    return summary, {'success_count': 1}


notification.send_lessons_refresh_notifications = SimpleNamespace(run=notify)
notification.deliver_admin_report = report
app = Celery('tableparser_crash_worker', fixups=[],
    broker=f'redis://127.0.0.1:{port}/0', backend=f'redis://127.0.0.1:{port}/1',
    include=['schedule_ingestion.tasks'])
app.conf.update(task_serializer='json', result_serializer='json', accept_content=['json'],
                result_expires=300, worker_prefetch_multiplier=1)
app.set_default()
