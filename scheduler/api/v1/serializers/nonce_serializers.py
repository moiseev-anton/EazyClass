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
            logger.info("auth.nonce.bound")
            return "authenticated"
        except Exception as e:
            # Cache exceptions may include the nonce or connection credentials.
            logger.error("auth.nonce.bind_failed error_type=%s", type(e).__name__)
            return "failed"
