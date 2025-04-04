from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dependency_injector import containers, providers

from telegrambot.api_client import ApiClient
from telegrambot.cache import CacheManager
from telegrambot.keyboards import KeyboardManager
from telegrambot.message_manager import MessageManager
from telegrambot.services import UserService, CacheService


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    api_client = providers.Singleton(
        ApiClient,
        base_url=config.api_base_url,
        hmac_secret=config.hmac_secret,
        platform=config.platform,
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

    cache_manager = providers.Singleton(CacheManager)

    keyboard_manager = providers.Singleton(KeyboardManager, cache_manager=cache_manager)
    message_manager = providers.Singleton(MessageManager, cache_manager=cache_manager)

    cache_service = providers.Factory(
        CacheService,
        api_client=api_client,
        faculties_cache_file=config.faculties_cache_file,
        teachers_cache_file=config.teachers_cache_file,
        cache_manager=cache_manager,
    )

    user_service = providers.Factory(UserService, api_client=api_client)
