import hashlib
import hmac
import logging
import sys
import time

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from scheduler.models import SocialAccount

logger = logging.getLogger(__name__)

HMAC_TIMEOUT = 180  # 3 минуты


class HMACAuthentication(BaseAuthentication):

    @staticmethod
    def _verify_hmac_signature(request, platform: str, social_id: str, timestamp: str, signature: str) -> bool:
        """Проверяет HMAC-подпись запроса."""
        hmac_secret = settings.BOT_HMAC_SECRETS.get(platform)
        if not hmac_secret:
            return False

        # Воссоздаем изначальную строку
        method = request.method
        url = request.build_absolute_uri()
        body_hash = hashlib.sha256(request.body).hexdigest()
        data = f"{method}\n{url}\n{timestamp}\n{platform}\n{social_id}\n{body_hash}".encode("utf-8")

        # Получаем HMAC и сравниваем
        expected_signature = hmac.new(hmac_secret.encode("utf-8"), data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_signature, signature)

    def authenticate(self, request):
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        platform = request.headers.get("X-Platform")  # "telegram" или "vk"
        social_id = request.headers.get("X-Social-ID")  # ID в соцсети

        if not all([platform, signature, timestamp, social_id]):
            return None  # Даем шанс другим методам аутентификации

        # Проверка временной метки
        try:
            if abs(time.time() - int(timestamp)) > HMAC_TIMEOUT:
                raise AuthenticationFailed("Timestamp out of range.")
        except ValueError:
            raise AuthenticationFailed("Invalid timestamp format.")

        # Проверяем HMAC-подпись
        if not self._verify_hmac_signature(request, platform, social_id, timestamp, signature):
            raise AuthenticationFailed("Invalid HMAC signature.")

        try:
            social_account = SocialAccount.objects.select_related("user").get(platform=platform, social_id=social_id)
            return social_account.user, None
        except SocialAccount.DoesNotExist:
            return None, None
