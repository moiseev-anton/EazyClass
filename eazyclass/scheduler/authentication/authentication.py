import hashlib
import hmac
import time

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from scheduler.models import SocialAccount


class HMACAuthentication(BaseAuthentication):

    @staticmethod
    def _verify_hmac_signature(request, provider: str, social_id: str, timestamp: str, signature: str) -> bool:
        """Проверяет HMAC-подпись запроса."""
        hmac_secret = settings.BOT_HMAC_SECRETS.get(provider)
        if not hmac_secret:
            return False

        # Формируем сообщение, включая метод, URL и тело
        method = request.method
        url = request.build_absolute_uri()
        body_hash = hashlib.sha256(request.body).hexdigest()
        data = f"{method}\n{url}\n{timestamp}\n{provider}\n{social_id}\n{body_hash}".encode()

        expected_signature = hmac.new(hmac_secret.encode(), data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected_signature, signature)

    def authenticate(self, request):
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        provider = request.headers.get("X-Provider")  # "telegram" или "vk"
        social_id = request.headers.get("X-Social-ID")  # ID в соцсети

        if not all([provider, signature, timestamp, social_id]):
            return None  # Даем шанс другим методам аутентификации

        # Проверка временной метки
        try:
            if abs(time.time() - int(timestamp)) > 300:
                raise AuthenticationFailed("Timestamp out of range.")
        except ValueError:
            raise AuthenticationFailed("Invalid timestamp format.")

        # Проверяем HMAC-подпись
        if not self._verify_hmac_signature(request, provider, social_id, timestamp, signature):
            raise AuthenticationFailed("Invalid HMAC signature.")

        try:
            social_account = SocialAccount.objects.select_related("user").get(provider=provider, social_id=social_id)
            return social_account.user, None  # `None` вместо токена, так как он не нужен
        except SocialAccount.DoesNotExist:
            raise AuthenticationFailed("User not found.")
