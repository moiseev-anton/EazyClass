"""Isolated synchronization tests with SQLite and no external services."""
from .broadcast_settings import *

INSTALLED_APPS = [*INSTALLED_APPS, "django_celery_beat"]
BASE_SCRAPING_URL = "https://example.invalid/"
TIME_ZONE = "Europe/Moscow"
