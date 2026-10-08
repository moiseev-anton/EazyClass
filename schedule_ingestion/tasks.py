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


@shared_task(queue='periodic_tasks')
def publish_revision(revision_id, *, request_id, resolved_range, requested_by, automatic):
    from .publication import prepare_publication, apply_publication
    publication = prepare_publication(revision_id, request_id=request_id,
        resolved_range=resolved_range, requested_by=requested_by, automatic=automatic)
    return str(apply_publication(publication.pk).pk)


@shared_task(queue='periodic_tasks')
def notify_publication(publication_id):
    from .delivery import deliver_publication
    deliver_publication(publication_id, 'notifications')
    return publication_id


@shared_task(queue='periodic_tasks')
def report_publication(publication_id):
    from .delivery import deliver_publication
    deliver_publication(publication_id, 'report')
    return publication_id


@shared_task(queue='periodic_tasks')
def apply_saved_publication(publication_id):
    from .publication import apply_publication
    return str(apply_publication(publication_id).pk)


def resume_publication_chain(publication_id):
    """Resume the saved identity and bounds, without fetching or parsing again."""
    return chain(apply_saved_publication.s(str(publication_id)),
                 notify_publication.s(), report_publication.s())


def publication_chain(revision_id, *, requested_by, automatic=False, start_day_offset=0, end_day_offset=None):
    import uuid
    from scheduler.dtos.lesson_sync_range import LessonSyncRange
    bounds = LessonSyncRange.from_offsets(start_day_offset=start_day_offset, end_day_offset=end_day_offset)
    return chain(publish_revision.s(str(revision_id), request_id=str(uuid.uuid4()),
        resolved_range=bounds.to_dict(), requested_by=requested_by, automatic=automatic),
        notify_publication.s(), report_publication.s())


def source_refresh_chain(source_id, *, start_day_offset=0, end_day_offset=None):
    import uuid
    from scheduler.dtos.lesson_sync_range import LessonSyncRange
    bounds = LessonSyncRange.from_offsets(start_day_offset=start_day_offset, end_day_offset=end_day_offset)
    return chain(fetch_source.s(source_id), parse_run.s(),
        publish_revision.s(request_id=str(uuid.uuid4()), resolved_range=bounds.to_dict(),
                           requested_by='celery', automatic=True),
        notify_publication.s(), report_publication.s())


@shared_task(queue='periodic_tasks')
def start_source_refresh(source_id, *, start_day_offset=0, end_day_offset=None):
    return source_refresh_chain(source_id, start_day_offset=start_day_offset,
                               end_day_offset=end_day_offset).apply_async().id
