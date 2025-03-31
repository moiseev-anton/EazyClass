from dependency_injector import containers, providers
from telegrambot.api_client import APIClient
from telegrambot.services import UserService
from telegrambot.keyboards import KeyboardManager
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage


class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    api_client = providers.Singleton(
        APIClient,
        base_url=config.api_base_url,
        hmac_secret=config.hmac_secret,
        provider=config.provider
    )

    # Factory для UserService
    user_service = providers.Factory(
        UserService,
        backend_client=api_client
    )

    # Singleton для KeyboardManager
    keyboard_manager = providers.Singleton(
        KeyboardManager,
        backend_client=api_client
    )

    bot = providers.Singleton(
        Bot,
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    storage = providers.Singleton(
        RedisStorage.from_url,
        url=config.redis_storage_url
    )


