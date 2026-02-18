import hashlib
import hmac
import json
import logging
import time
from urllib.parse import parse_qsl

from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from scheduler.models.social_account_model import Platform

logger = logging.getLogger(__name__)


class TelegramWebAppAuthentication(BaseAuthentication):
    """
    Аутентификация через Telegram WebApp initData.
    Ожидает заголовок:
    Authorization: tma <initData>
    """

    keyword = "tma"
    max_age_seconds = 300  # защита от replay

    def authenticate(self, request):
        header = request.headers.get("Authorization")
        if not header:
            return None

        try:
            scheme, init_data = header.split(" ", 1)
        except ValueError:
            raise AuthenticationFailed("Invalid Authorization header")

        if scheme.lower() != self.keyword:
            return None

        data = self._validate_init_data(init_data)
        user = self._get_or_create_user(data)

        return user, "telegram_webapp"

    def _validate_init_data(self, init_data: str) -> dict:
        parsed = dict(parse_qsl(init_data, strict_parsing=True))

        received_hash = parsed.pop("hash", None)
        if not received_hash:
            raise AuthenticationFailed("Missing hash")

        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData", settings.TELEGRAM_BOT_TOKEN.encode(), hashlib.sha256
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.info("TWA auth: signature mismatch")
            raise AuthenticationFailed("Invalid Telegram signature")

        auth_date = int(parsed.get("auth_date", 0))
        age = time.time() - auth_date

        if age > self.max_age_seconds:
            logger.info("TWA auth: initData expired")
            raise AuthenticationFailed("initData expired")

        return parsed

    def _get_or_create_user(self, data: dict):
        telegram_user = json.loads(data["user"])

        social_id = str(telegram_user["id"])
        chat_id = None
        if chat := data.get("chat"):
            chat_obj = json.loads(chat)
            if chat_id_raw := chat_obj.get("id"):
                chat_id = str(chat_id_raw)

        User = get_user_model()

        user, created = User.objects.get_or_create_user(
            social_id=social_id,
            platform=Platform.TELEGRAM.value,
            chat_id=chat_id,
            first_name=telegram_user.get("first_name"),
            last_name=telegram_user.get("last_name"),
            extra_data=telegram_user,
        )

        logger.info(
            f"TWA auth: user {'created' if created else 'loaded'} id={user.id}"
        )

        return user
