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
            logger.error(f"Nonce {nonce} bound for user {user_id}.")
            return "authenticated"
        except Exception as e:
            logger.error(f"Failed to bind nonce {nonce} for user {user_id}: {str(e)}")
            return "failed"
