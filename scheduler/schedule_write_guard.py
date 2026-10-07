"""One transactional writer across legacy and version-addressed synchronization."""
from contextlib import contextmanager

from django.db import connection, transaction
from django.dispatch import Signal

schedule_applied = Signal()


@contextmanager
def schedule_write_guard():
    with transaction.atomic():
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [734921650812])
        elif connection.vendor != 'sqlite':
            raise ValueError('Unsupported schedule database')
        yield
