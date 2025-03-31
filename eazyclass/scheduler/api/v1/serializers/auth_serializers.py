import logging

from django.core.cache import caches
from rest_framework import serializers

from scheduler.models import User, SocialAccount, Provider

SOCIAL_ID_MAX_LENGTH = SocialAccount._meta.get_field('social_id').max_length
PROVIDER_MAX_LENGTH = SocialAccount._meta.get_field('provider').max_length
FIRST_NAME_MAX_LENGTH = User._meta.get_field('first_name').max_length
LAST_NAME_MAX_LENGTH = User._meta.get_field('last_name').max_length

logger = logging.getLogger(__name__)
cache = caches['auth']


class NonceSerializer(serializers.Serializer):
    nonce = serializers.UUIDField(required=False)

    def save_nonce(self, user_id: str, timeout: int = 300) -> str:
        """Сохраняет nonce в Redis, если он передан, и возвращает статус."""
        nonce = self.validated_data.get("nonce")
        if nonce:
            try:
                cache.set(str(nonce), user_id, timeout=timeout)
                logger.info(f"User {user_id} authenticated with nonce {nonce}")
                return "authenticated"

            except Exception as e:  # Общее исключение для совместимости с любым бэкендом кеша
                logger.error(f"Failed to save nonce {nonce} for user {user_id} in cache: {str(e)}")
                return "failed"

        logger.debug(f"User {user_id} started bot without nonce")
        return "none"


class BotAuthSerializer(serializers.Serializer):
    social_id = serializers.CharField(
        max_length=SOCIAL_ID_MAX_LENGTH,
        required=True
    )
    provider = serializers.ChoiceField(
        choices=Provider.choices,
    )
    first_name = serializers.CharField(
        max_length=FIRST_NAME_MAX_LENGTH,
        required=False, allow_blank=True,
        allow_null=True
    )
    last_name = serializers.CharField(
        max_length=LAST_NAME_MAX_LENGTH,
        required=False,
        allow_blank=True,
        allow_null=True
    )
    extra_data = serializers.JSONField(
        required=False,
        allow_null=True
    )

    def create(self, validated_data):
        social_id = validated_data['social_id']
        provider = validated_data['provider']
        first_name = validated_data['first_name']
        last_name = validated_data['last_name']
        extra_data = validated_data.get('extra_data', {})

        user, created = User.objects.get_or_create_user(
            social_id=social_id,
            provider=provider,
            first_name=first_name,
            last_name=last_name,
            extra_data=extra_data
        )

        return user, created

    def save(self, **kwargs):
        return self.create(self.validated_data)
