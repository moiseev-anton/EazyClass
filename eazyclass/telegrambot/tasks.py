import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from telegrambot.config import settings
from telegrambot.dependencies import Container

logger = logging.getLogger(__name__)


async def setup_periodic_task_scheduler(deps: Container) -> AsyncIOScheduler:
    """Настройка и запуск планировщика"""
    scheduler = deps.scheduler()

    async def update_keyboards():
        try:
            await deps.cache_service().update_all()
        except Exception as e:
            logger.error(f"Scheduled update failed: {e}")

    # Обновление клавиатур с заданной периодичностью
    scheduler.add_job(
        update_keyboards,
        **settings.update_keyboards_rule,
        id="daily_keyboard_update",
    )

    scheduler.start()
    return scheduler
