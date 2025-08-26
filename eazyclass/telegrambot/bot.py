import asyncio
import logging
import sys

from aiogram import Dispatcher

from config import settings
from dependencies import Container
from telegrambot.handlers import (
    start_router,
    main_router,
    faculty_router,
    teacher_router,
    navigation_router,
    action_router,
)
from telegrambot.middleware import UserContextMiddleware
from telegrambot.tasks import setup_periodic_task_scheduler

import jsonapi_client
from telegrambot.api_client.client_patch import camelize_attribute_name, decamelize_attribute_name
from telegrambot.api_client.document import CustomDocument


logging.basicConfig(level=getattr(logging, settings.log_level), stream=sys.stdout)
logger = logging.getLogger(__name__)


# Хуки запуска и остановки
async def on_startup(deps: Container):
    api_client = deps.api_client()
    cache_service = deps.cache_service()
    await cache_service.update_all()  # Первичное обновление клавиатур
    await setup_periodic_task_scheduler(deps=deps)  # Запуск планировщика
    logger.info("Bot started.")


async def on_shutdown(deps: Container):
    api_client = deps.api_client()
    await api_client.close()
    logger.info("Bot stopped.")


async def main():
    # Monkey-патч для jsonapi_client
    jsonapi_client.common.jsonify_attribute_name = camelize_attribute_name
    jsonapi_client.common.dejsonify_attribute_name = decamelize_attribute_name
    jsonapi_client.document.Document = CustomDocument

    container = Container()
    container.config.from_pydantic(settings)

    bot = container.bot()
    storage = container.storage()
    dp = Dispatcher(bot=bot, storage=storage, deps=container)
    dp.message.middleware(UserContextMiddleware())
    dp.callback_query.middleware(UserContextMiddleware())

    dp.include_router(action_router)
    dp.include_router(start_router)
    dp.include_router(main_router)
    dp.include_router(faculty_router)
    dp.include_router(teacher_router)
    dp.include_router(navigation_router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

