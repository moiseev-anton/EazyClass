"""Actual scheduler models, isolated DB, no production settings or services."""
from scheduler.tests.broadcast_settings import *

INSTALLED_APPS = [*INSTALLED_APPS, 'schedule_ingestion']
TIME_ZONE = 'Europe/Moscow'
# Sync scheduler and its FK targets together before applying ingestion migrations.
# PostgreSQL cannot create scheduler FKs to yet-unmigrated auth/contenttype tables.
MIGRATION_MODULES = {'scheduler': None, 'auth': None, 'contenttypes': None}
