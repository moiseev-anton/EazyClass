import logging
from time import perf_counter

from eazyclass.logging_config import safe_error_context

from django.conf import settings

from celery import chain, shared_task

from scheduler.dtos.lesson_sync_range import LessonSyncRange
from scheduler.tasks.scraping import run_schedule_spider
from scheduler.tasks.synchronisation import sync_lessons
from scheduler.tasks.notification import (
    send_admin_report,
    send_lessons_refresh_notifications,
)
from scheduler.tasks.extract_raw_lessons import process_google_schedule


from scheduler.fetched_data_sync import refresh_faculties_and_groups, refresh_teachers_endpoints

logger = logging.getLogger(__name__)

BASE_URL = settings.BASE_SCRAPING_URL
GROUPS_PAGE_LINK = "grupp.php"
TEACHERS_PAGE_PATH = "prep.php"


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def refresh_groups(self, base_url: str = BASE_URL, endpoint:str = GROUPS_PAGE_LINK):
    started = perf_counter()
    logger.info("Начинается обновление факультетов и групп",
                extra={"event": "reference.groups.started"})
    try:
        counts = refresh_faculties_and_groups(base_url=base_url, endpoint=endpoint)
    except Exception as e:
        _log_refresh_failure(self, "groups", "Обновление факультетов и групп", started, e)
        raise self.retry(exc=e)
    logger.info(
        "Факультеты и группы обновлены: получено факультетов %s, групп %s; деактивировано факультетов %s, групп %s",
        counts["faculties_count"], counts["groups_count"],
        counts["deactivated_faculties_count"], counts["deactivated_groups_count"],
        extra={"event": "reference.groups.completed", "outcome": "success", **counts,
               "duration_ms": round((perf_counter() - started) * 1000, 3)},
    )
    
@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def refresh_teachers(self, base_url: str = BASE_URL, page_path:str = TEACHERS_PAGE_PATH):
    started = perf_counter()
    logger.info("Начинается обновление адресов страниц преподавателей",
                extra={"event": "reference.teachers.started"})
    try:
        counts = refresh_teachers_endpoints(base_url=base_url, page_path=page_path)
    except Exception as e:
        _log_refresh_failure(self, "teachers", "Обновление адресов преподавателей", started, e)
        raise self.retry(exc=e)
    outcome = "empty" if counts["count"] == 0 else "partial" if counts["unmatched_count"] else "success"
    logger.log(
        logging.INFO if outcome == "success" else logging.WARNING,
        "Обновление адресов преподавателей завершено: получено %s, изменено %s, без изменений %s, не сопоставлено %s",
        counts["count"], counts["updated_count"], counts["unchanged_count"], counts["unmatched_count"],
        extra={"event": "reference.teachers.completed", "outcome": outcome, **counts,
               "duration_ms": round((perf_counter() - started) * 1000, 3)},
    )


def _log_refresh_failure(task, resource, operation, started, exc):
    retry_available = task.request.retries < task.max_retries
    outcome = "retry_requested" if retry_available else "failed"
    logger.log(
        logging.WARNING if retry_available else logging.ERROR,
        "%s не завершено; %s", operation,
        "запрашивается повтор" if retry_available else "попытки исчерпаны",
        extra={"event": f"reference.{resource}.{outcome}", "outcome": outcome,
               "attempt": task.request.retries + 1,
               "duration_ms": round((perf_counter() - started) * 1000, 3),
               **safe_error_context(exc)},
    )


# Resolve once so scraping and synchronization use the same range across midnight.
@shared_task(queue="periodic_tasks")
def run_lessons_refresh_pipeline(*, start_day_offset=0, end_day_offset=None):
    date_range = LessonSyncRange.from_offsets(
        start_day_offset=start_day_offset, end_day_offset=end_day_offset
    )
    chain(
        run_schedule_spider.s(cache_scope=date_range.cache_scope),
        sync_lessons.s(_resolved_range=date_range.to_dict()),
        send_lessons_refresh_notifications.s(),
        send_admin_report.s(),
    ).apply_async()


@shared_task(queue="periodic_tasks")
def run_lessons_refresh_by_google_docs(*, start_day_offset=0, end_day_offset=None):
    date_range = LessonSyncRange.from_offsets(
        start_day_offset=start_day_offset, end_day_offset=end_day_offset
    )
    chain(
        process_google_schedule.s(),
        sync_lessons.s(_resolved_range=date_range.to_dict()),
        send_lessons_refresh_notifications.s(),
        send_admin_report.s(),
    ).apply_async()
