from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from kombu import Queue

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eazyclass.settings')

app = Celery('eazyclass')

# Загрузка настроек из Django.
app.config_from_object('django.conf:settings', namespace='CELERY')

app.conf.task_queues = (
    Queue('bot_tasks', routing_key='bot.#'),
    Queue('periodic_tasks', routing_key='periodic.#'),
    Queue('default', routing_key='task.#'),
)

app.conf.task_default_queue = 'default'
app.conf.task_default_exchange = 'tasks'
app.conf.task_default_routing_key = 'task.default'

# Автоматическое обнаружение задач из всех django apps.
app.autodiscover_tasks()

