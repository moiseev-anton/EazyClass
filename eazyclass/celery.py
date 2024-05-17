from __future__ import absolute_import, unicode_literals
import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eazyclass.settings')

app = Celery('eazyclass')

# Загрузка настроек из Django.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматическое обнаружение задач из всех django apps.
app.autodiscover_tasks()