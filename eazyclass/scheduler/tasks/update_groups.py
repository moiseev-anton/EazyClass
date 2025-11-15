import logging

from celery import shared_task
from django.conf import settings

from scheduler.fetched_data_sync import update_faculties_and_groups

logger = logging.getLogger(__name__)

BASE_URL = settings.BASE_SCRAPING_URL
GROUPS_PAGE_LINK = "grupp.php"


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def update_groups(self, base_url: str = BASE_URL, endpoint:str = GROUPS_PAGE_LINK):
    try:
        update_faculties_and_groups(base_url=base_url, endpoint=endpoint)
    except Exception as e:
        logger.error(f"Ошибка при обновлении факультетов и групп: {e}")
        raise self.retry(exc=e)
