import logging

from django.core.cache import caches
from rest_framework import serializers

logger = logging.getLogger(__name__)
cache = caches["auth"]


class NonceSerializer(serializers.Serializer):
    nonce = serializers.UUIDField()

    def save_nonce(self, user_id: str, timeout: int = 300) -> str:
        """Сохраняет nonce в Redis, и возвращает статус."""
        nonce = str(self.validated_data["nonce"])
        try:
            cache.set(nonce, user_id, timeout=timeout)
            logger.info(
                "Одноразовый код авторизации привязан к пользователю",
                extra={"event": "auth.nonce.bound", "user_id": user_id},
            )
            return "authenticated"
        except Exception as e:
            # Cache exceptions may include the nonce or connection credentials.
            logger.error(
                "Не удалось привязать одноразовый код авторизации к пользователю",
                extra={"event": "auth.nonce.bind_failed", "user_id": user_id,
                       "error_type": type(e).__name__},
            )
            return "failed"
