import logging
from typing import Any

from celery import shared_task

from scheduler.dtos import PipelineSummary
from scheduler.scrapied_data_sync import LessonsSyncManager

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def sync_schedule(self, _: Any = None):
    """
    Задача для синхронизации данных из Redis в БД.
    Параметр _ используется только для поддержки передачи аргументов в цепочке задач.
    """
    logger.info("Запуск задачи синхронизации расписания ...")
    try:
        sync_manager = LessonsSyncManager()
        sync_summary = sync_manager.update_schedule()
        logger.info("Завершение задачи синхронизации.")

        pipeline_summary = PipelineSummary(sync_summary=sync_summary)
        pipeline_summary.spider_result = sync_manager.fetched_data_summary
        return pipeline_summary.model_dump()
    except Exception as e:
        logger.error(f"Задача синхронизации расписания провалилась: {e}")
        raise self.retry(exc=e)
