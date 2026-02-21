import logging

from django.conf import settings

from celery import chain, shared_task

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
    try:
        refresh_faculties_and_groups(base_url=base_url, endpoint=endpoint)
    except Exception as e:
        logger.error(f"Ошибка при обновлении факультетов и групп: {e}")
        raise self.retry(exc=e)
    
@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def refresh_teachers(self, base_url: str = BASE_URL, page_path:str = TEACHERS_PAGE_PATH):
    try:
        refresh_teachers_endpoints(base_url=base_url, page_path=page_path)
    except Exception as e:
        logger.error(f"Ошибка при обновлении учителей: {e}")
        raise self.retry(exc=e)


# Цепочка: spider -> sync -> telegram_notifications
@shared_task(queue="periodic_tasks")
def run_lessons_refresh_pipeline():
        chain(
            run_schedule_spider.s(),
            sync_lessons.s(),
            send_lessons_refresh_notifications.s(),
            send_admin_report.s(),
        ).apply_async()


# Цепочка: file_rider -> sync -> telegram_notifications
@shared_task(queue="periodic_tasks")
def run_lessons_refresh_by_google_docs():
        chain(
            process_google_schedule.s(),
            sync_lessons.s(),
            send_lessons_refresh_notifications.s(),
            send_admin_report.s(),
        ).apply_async()