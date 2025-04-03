from typing import Optional, Dict, Any
from aiogram.types import User
from telegrambot.api_client import ApiClient
import logging

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, api_client: ApiClient):
        self.api_client = api_client

    async def register_or_login_user(self, tlg_user: User, nonce: Optional[str] = None) -> Dict[str, Any]:
        social_id = str(tlg_user.id)
        payload = {
            "social_id": social_id,
            "platform": 'telegram',
            "first_name": tlg_user.first_name or "",
            "last_name": tlg_user.last_name or "",
            "extra_data": {
                "username": tlg_user.username,
                "language_code": tlg_user.language_code,
                "is_premium": tlg_user.is_premium,
                "added_to_attachment_menu": tlg_user.added_to_attachment_menu,
            },
        }

        if nonce:
            payload["nonce"] = nonce
        try:
            response = await self.api_client.request(social_id=social_id, endpoint="bot/", method="POST", payload=payload)
            return response
        except Exception as e:
            logger.error(f"Failed to register/login user {social_id}: {str(e)}")
            raise

