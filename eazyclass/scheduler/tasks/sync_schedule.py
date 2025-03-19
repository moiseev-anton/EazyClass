from celery import shared_task, chain
import logging
from scheduler.scrapied_data_sync.schedule_updater import ScheduleSyncManager
from scheduler.tasks import run_schedule_spider


logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def sync_schedule(self):
    """Задача для синхронизации данных из Redis в БД."""
    logger.info("Запуск синхронизации расписания ...")
    try:
        sync_manager = ScheduleSyncManager()
        sync_manager.update_schedule()
        logger.info("Синхронизация расписания завершена.")
    except Exception as e:
        logger.error(f"Ошибка при синхронизации расписания: {e}")
        raise self.retry(exc=e)


@shared_task(bind=True, max_retries=0, default_retry_delay=60, queue='periodic_tasks')
def run_spider_and_sync_schedule(self):
    chain(
        run_schedule_spider.s(),
        sync_schedule.s()
    ).apply_async()