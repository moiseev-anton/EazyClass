import logging
from time import perf_counter
from typing import Any

import orjson
from celery import shared_task

from eazyclass.logging_config import safe_error_context

from scheduler.dtos.lesson_sync_range import LessonSyncRange
from scheduler.dtos import PipelineSummary
from scheduler.fetched_data_sync import LessonsSyncManager
from utils import RedisClientManager
from enums import KeyEnum

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=60, queue="periodic_tasks")
def sync_lessons(self, _: Any = None, *, start_day_offset: int = 0,
                 end_day_offset: int | None = None, _resolved_range: dict | None = None):
    """
    Синхронизирует полученные данные уроков с данными БД.
    Параметр _ используется только для поддержки передачи аргументов в цепочке задач.
    _resolved_range — внутренние границы от родительской задачи или retry.
    """
    if _resolved_range is not None:
        if type(start_day_offset) is not int or start_day_offset != 0 or end_day_offset is not None:
            raise ValueError("Resolved range cannot be combined with day offsets")
        date_range = LessonSyncRange.from_dict(_resolved_range)
    else:
        date_range = LessonSyncRange.from_offsets(
            start_day_offset=start_day_offset, end_day_offset=end_day_offset
        )
    started = perf_counter()
    context = {"start_date": date_range.start.isoformat(),
               "end_date": date_range.end.isoformat() if date_range.end else None}
    logger.info(
        "Начинается синхронизация расписания: с %s по %s",
        context["start_date"], context["end_date"] or "последнюю доступную дату",
        extra={"event": "schedule.sync.started", **context},
    )
    stage = "load_and_apply"
    try:
        redis_client = RedisClientManager.get_client("scrapy")

        sync_manager = LessonsSyncManager(
            redis_client=redis_client, start_sync_day=date_range.start, end_sync_day=date_range.end
        )
        sync_summary = sync_manager.update_schedule()
        stage = "build_report"
        scrapy_summary_json = redis_client.get(KeyEnum.SCRAPY_SUMMARY)
        scrapy_summary = orjson.loads(scrapy_summary_json)

        pipeline_summary = PipelineSummary(sync_summary=sync_summary)
        pipeline_summary.spider_result = scrapy_summary
        result = pipeline_summary.model_dump()
        counts = {f"{key}_count": len(sync_summary[key]) for key in ("added", "updated", "removed")}
        logger.info(
            "Синхронизация завершена: добавлено %s, изменено %s, удалено %s занятий",
            counts["added_count"], counts["updated_count"], counts["removed_count"],
            extra={"event": "schedule.sync.completed", "outcome": "success", **context, **counts,
                   "duration_ms": round((perf_counter() - started) * 1000, 3)},
        )
        return result
    except Exception as e:
        retry_available = self.request.retries < self.max_retries
        logger.log(
            logging.WARNING if retry_available else logging.ERROR,
            "Синхронизация не завершена; запрашивается повтор" if retry_available
            else "Синхронизация не завершена: попытки исчерпаны",
            extra={"event": "schedule.sync.retry_requested" if retry_available else "schedule.sync.failed",
                   "outcome": "retry_requested" if retry_available else "failed",
                   "stage": stage, "attempt": self.request.retries + 1, **context,
                   "duration_ms": round((perf_counter() - started) * 1000, 3), **safe_error_context(e)},
        )
        raise self.retry(exc=e, args=(), kwargs={"_": _, "_resolved_range": date_range.to_dict()})
