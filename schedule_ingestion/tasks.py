"""Opt-in parsing and publication chains; no beat schedule is created implicitly."""
from celery import chain, shared_task
from django.conf import settings

from .acquisition import acquire_source
from .google_sheets import SheetTransportError
from .parse_execution import execute_parse, ParseBusy


def runtime_options():
    profile = settings.TABLEPARSER_RUNTIME
    return dict(resource_root=profile['resource_root'], catalog_source=profile['catalog_source'])


@shared_task(bind=True, queue='periodic_tasks', max_retries=3, default_retry_delay=60)
def fetch_source(self, source_id):
    try:
        run = acquire_source(source_id, acquisition_id=self.request.id, **runtime_options())
        return str(run.pk)
    except SheetTransportError as error:
        raise self.retry(exc=error)


@shared_task(bind=True, queue='periodic_tasks', max_retries=3, default_retry_delay=60)
def parse_run(self, run_id):
    try:
        return str(execute_parse(run_id, **runtime_options()).pk)
    except ParseBusy as error:
        raise self.retry(exc=error)


def source_parse_chain(source_id):
    return chain(fetch_source.s(source_id), parse_run.s())


@shared_task(queue='periodic_tasks')
def start_source_parse(source_id):
    """Each explicit invocation starts a fresh fetch task with its own identity."""
    return source_parse_chain(source_id).apply_async().id
