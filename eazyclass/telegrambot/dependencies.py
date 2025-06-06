from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dependency_injector import containers, providers

from telegrambot.api_client import JsonApiClient, HmacJsonApiClient
from telegrambot.cache import CacheRepository
from telegrambot.managers.keyboard_manager import KeyboardManager
from telegrambot.managers.message_manager import MessageManager
from telegrambot.services import UserService, CacheService, LessonService


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    api_client = providers.Singleton(
        HmacJsonApiClient,
        server_url=config.api_base_url,
        hmac_secret=config.hmac_secret,
        platform=config.platform,
        bot_social_id=config.bot_social_id,
    )

    bot = providers.Singleton(
        Bot,
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    storage = providers.Singleton(
        RedisStorage.from_url,
        url=config.redis_storage_url,
        state_ttl=config.storage_state_ttl,
        data_ttl=config.storage_data_ttl,
    )

    scheduler = providers.Singleton(AsyncIOScheduler)

    cache_repository = providers.Singleton(CacheRepository)

    keyboard_manager = providers.Singleton(KeyboardManager, cache_repository=cache_repository)
    message_manager = providers.Singleton(MessageManager, cache_repository=cache_repository)

    cache_service = providers.Factory(
        CacheService,
        api_client=api_client,
        faculties_cache_file=config.faculties_cache_file,
        teachers_cache_file=config.teachers_cache_file,
        cache_repository=cache_repository,
    )

    user_service = providers.Factory(UserService, api_client=api_client)
    lesson_service = providers.Factory(LessonService, api_client=api_client)

