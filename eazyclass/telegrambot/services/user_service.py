import logging
from typing import Optional, Dict, Any

from aiogram.types import User as TelegramUser
from jsonapi_client.resourceobject import ResourceObject
from telegrambot.api_client import AsyncClientSession
from telegrambot.context import set_hmac

logger = logging.getLogger(__name__)


class UserService:
    REGISTER_URL = "/register/"
    REGISTER_WITH_NONCE_URL = "/register_with_nonce/"

    def __init__(self, api_client: AsyncClientSession, user: TelegramUser):
        self.api_client = api_client
        self.user = user

    async def register_user(self, nonce: Optional[str] = None) -> ResourceObject:
        social_id = str(self.user.id)

        # Формируем атрибуты для ресурса
        attrs = {
            "social_id": social_id,
            "platform": "telegram",
            "first_name": self.user.first_name or "",
            "last_name": self.user.last_name or "",
            "extra_data": {
                "username": self.user.username,
                "language_code": self.user.language_code,
                "is_premium": self.user.is_premium,
                "added_to_attachment_menu": self.user.added_to_attachment_menu,
            },
        }
        url_suffix = self.REGISTER_URL
        if nonce:
            attrs["nonce"] = nonce
            url_suffix = self.REGISTER_WITH_NONCE_URL

        user_resource = self.api_client.create(_type="user", **attrs)  # Используем **attrs вместо fields
        with set_hmac(True):
            await user_resource.commit(custom_url=f'{self.api_client.url_prefix}{url_suffix}')
        return user_resource


