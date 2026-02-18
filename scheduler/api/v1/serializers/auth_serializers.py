import logging
from dataclasses import dataclass

from rest_framework import status
from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import User, SocialAccount
from scheduler.models.social_account_model import Platform

SOCIAL_ID_MAX_LENGTH = SocialAccount._meta.get_field("social_id").max_length
CHAT_ID_MAX_LENGTH = SocialAccount._meta.get_field("chat_id").max_length
PLATFORM_MAX_LENGTH = SocialAccount._meta.get_field("platform").max_length
FIRST_NAME_MAX_LENGTH = User._meta.get_field("first_name").max_length
LAST_NAME_MAX_LENGTH = User._meta.get_field("last_name").max_length

logger = logging.getLogger(__name__)


@dataclass
class AuthResult:
    user: User
    social_account: SocialAccount
    created: bool

    @property
    def status_code(self) -> int:
        return status.HTTP_201_CREATED if self.created else status.HTTP_200_OK


class AuthSerializer(json_api_serializers.Serializer):
    social_id = json_api_serializers.CharField(
        max_length=SOCIAL_ID_MAX_LENGTH,
    )
    platform = json_api_serializers.ChoiceField(
        choices=Platform.choices,
    )
    chat_id = json_api_serializers.CharField(
        max_length=CHAT_ID_MAX_LENGTH,
    )
    first_name = json_api_serializers.CharField(
        max_length=FIRST_NAME_MAX_LENGTH,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    last_name = json_api_serializers.CharField(
        max_length=LAST_NAME_MAX_LENGTH,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    extra_data = json_api_serializers.JSONField(required=False, allow_null=True)

    class Meta:
        resource_name = "social-accounts"

    def create(self, validated_data) -> AuthResult:
        social_id = validated_data["social_id"]
        platform = validated_data["platform"]

        user, created = User.objects.get_or_create_user(
            platform=platform,
            social_id=social_id,
            chat_id=validated_data.get("chat_id"),
            first_name=validated_data.get("first_name") or "Anonymous",
            last_name=validated_data.get("last_name") or "",
            extra_data=validated_data.get("extra_data") or {},
        )

        social_account = user.accounts.get(
            platform=platform,
            social_id=social_id,
        )

        return AuthResult(user=user, social_account=social_account, created=created)

    def save(self, **kwargs) -> AuthResult:
        """Save and return SocialAccount instance."""
        return self.create(self.validated_data)

    def update(self, instance):
        updated_fields = []

        # Проверяем нужно ли обновить chat_id
        new_chat_id = self.validated_data.get("chat_id")
        if new_chat_id and new_chat_id != instance.chat_id:
            instance.chat_id = new_chat_id
            updated_fields.append("chat_id")

        # Проверяем, нужно ли обновить extra_data
        new_extra = self.validated_data.get("extra_data") or {}
        if new_extra != (instance.extra_data or {}):
            instance.extra_data = new_extra
            updated_fields.append("extra_data")

        # Если аккаунт был заблокирован — разблокируем
        if instance.is_blocked:
            instance.is_blocked = False
            updated_fields.append("is_blocked")

        if updated_fields:
            instance.save(update_fields=updated_fields)

        return instance


class AuthWithNonceSerializer(AuthSerializer):
    # Не участвует в сериализации. Нужен для автоматической документации API
    nonce = json_api_serializers.UUIDField(write_only=True)
