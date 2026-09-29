import hashlib
import hmac
import logging
import time

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from rest_framework.authentication import BaseAuthentication

from scheduler.models import SocialAccount
from scheduler.authentication.logging import authentication_rejected

logger = logging.getLogger(__name__)

HMAC_TIMEOUT = 60 * 3  # 3 минуты


class HMACAuthentication(BaseAuthentication):

    @staticmethod
    def _verify_hmac_signature(
        request, platform: str, social_id: str, timestamp: str, signature: str
    ) -> bool:
        """Проверяет HMAC-подпись запроса."""
        hmac_secret = settings.BOT_HMAC_SECRETS.get(platform)
        if not hmac_secret:
            return False

        # Воссоздаем изначальную строку
        method = request.method
        full_path = request.get_full_path()  # path_and_query
        body_hash = hashlib.sha256(request.body).hexdigest()

        data = f"{method}\n{full_path}\n{timestamp}\n{platform}\n{social_id}\n{body_hash}".encode("utf-8")
        # Получаем HMAC и сравниваем
        expected_signature = hmac.new(
            hmac_secret.encode("utf-8"), data, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected_signature, signature)

    def authenticate(self, request):
        signature = request.headers.get("X-Signature")
        timestamp = request.headers.get("X-Timestamp")
        platform = request.headers.get("X-Platform")  # "telegram" или "vk"
        social_id = request.headers.get("X-Social-ID")  # ID в соцсети

        if not all([platform, signature, timestamp, social_id]):
            logger.debug("HMAC-аутентификация пропущена: отсутствуют необходимые заголовки",
                         extra={"event": "auth.hmac.skipped", "reason": "missing_headers"})
            return None  # Даем шанс другим методам аутентификации

        # Проверка временной метки
        try:
            if abs(time.time() - int(timestamp)) > HMAC_TIMEOUT:
                raise authentication_rejected("Timestamp out of range.", "hmac_timestamp_out_of_range")
        except ValueError:
            raise authentication_rejected("Invalid timestamp format.", "hmac_invalid_timestamp")

        # Проверяем HMAC-подпись
        if not self._verify_hmac_signature(
            request, platform, social_id, timestamp, signature
        ):
            raise authentication_rejected("Invalid HMAC signature.", "hmac_signature_mismatch")

        try:
            social_account = SocialAccount.objects.select_related("user").get(
                platform=platform, social_id=social_id
            )
            logger.debug("Подпись HMAC проверена, пользователь найден",
                         extra={"event": "auth.hmac.verified", "user_id": social_account.user.pk})
            return social_account.user, "hmac"

        except SocialAccount.DoesNotExist:
            logger.debug("Подпись HMAC проверена, связанный аккаунт не найден",
                         extra={"event": "auth.hmac.anonymous", "reason": "account_not_found"})
            return AnonymousUser(), "hmac"
