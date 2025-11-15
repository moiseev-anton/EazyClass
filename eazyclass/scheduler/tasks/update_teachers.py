import logging

from celery import shared_task
from django.conf import settings

from scheduler.fetched_data_sync import update_teachers_endpoints

logger = logging.getLogger(__name__)

BASE_URL = settings.BASE_SCRAPING_URL
TEACHERS_PAGE_PATH = "prep.php"


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def update_teachers(self, base_url: str = BASE_URL, page_path:str = TEACHERS_PAGE_PATH):
    try:
        update_teachers_endpoints(base_url=base_url, page_path=page_path)
    except Exception as e:
        logger.error(f"Ошибка при обновлении учителей: {e}")
        raise self.retry(exc=e)