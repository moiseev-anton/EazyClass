from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.signals import (
    before_task_publish, setup_logging, task_postrun, task_prerun, worker_process_init,
)
from kombu import Queue

from eazyclass.logging_config import configure_service_logging
from eazyclass.logging_context import (
    clear_worker_context, publish_context, task_context_finished, task_context_started,
)

# Owning setup_logging prevents Celery from replacing the shared formatters.
setup_logging.connect(configure_service_logging, weak=False)
worker_process_init.connect(configure_service_logging, weak=False)
worker_process_init.connect(clear_worker_context, weak=False)
before_task_publish.connect(publish_context, weak=False)
task_prerun.connect(task_context_started, weak=False)
task_postrun.connect(task_context_finished, weak=False)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eazyclass.settings')

app = Celery('eazyclass')

# Загрузка настроек из Django.
app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.task_queues = (
    Queue('notifications', routing_key='notifications.#'),
    Queue('periodic_tasks', routing_key='periodic.#'),
    Queue('default', routing_key='task.#'),
)

app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'tasks'
app.conf.task_default_routing_key = 'task.default'

app.conf.broker_connection_retry_on_startup = True

# Автоматическое обнаружение задач из всех django apps.
app.autodiscover_tasks()

