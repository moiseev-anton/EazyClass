import logging
from typing import Any

import orjson
from celery import shared_task

from scheduler.dtos import PipelineSummary
from scheduler.fetched_data_sync import LessonsSyncManager
from utils import RedisClientManager
from enums import KeyEnum

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60, queue="periodic_tasks")
def sync_lessons(self, _: Any = None):
    """
    Синхронизирует полученные данные уроков с данными БД.
    Параметр _ используется только для поддержки передачи аргументов в цепочке задач.
    """
    logger.info("Запуск задачи синхронизации расписания ...")
    try:
        redis_client = RedisClientManager.get_client("scrapy")

        sync_manager = LessonsSyncManager(redis_client=redis_client)
        sync_summary = sync_manager.update_schedule()
        logger.info("Завершение задачи синхронизации.")

        scrapy_summary_json = redis_client.get(KeyEnum.SCRAPY_SUMMARY)
        scrapy_summary = orjson.loads(scrapy_summary_json)

        pipeline_summary = PipelineSummary(sync_summary=sync_summary)
        pipeline_summary.spider_result = scrapy_summary
        return pipeline_summary.model_dump()
    except Exception as e:
        logger.error(f"Задача синхронизации расписания провалилась: {e}", exc_info=True)
        raise self.retry(exc=e)
