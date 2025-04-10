import logging
from typing import Optional, Dict, Any

from aiogram.types import User

from telegrambot.api_client import ApiClient

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, api_client: ApiClient, user: User):
        self.api_client = api_client
        self.user = user

    async def register_or_login_user(
        self, nonce: Optional[str] = None
    ) -> Dict[str, Any]:
        social_id = str(self.user.id)
        payload = {
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

        if nonce:
            payload["nonce"] = nonce
        try:
            response = await self.api_client.request(
                social_id=social_id, endpoint="bot/", method="POST", payload=payload
            )
            if response.get("success"):
                return response.get("data")

            error = response.get("errors", {})
            logger.error(f"API error: {error.get('code', 'unknown')} - {error.get('message', 'No message')}")
            raise Exception(f"API error: {error.get('message', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Failed to register/login user {social_id}: {str(e)}")
            raise



