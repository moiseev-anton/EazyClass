import logging
from dataclasses import dataclass

from rest_framework import status
from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import User, SocialAccount, Platform

SOCIAL_ID_MAX_LENGTH = SocialAccount._meta.get_field("social_id").max_length
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
        new_extra = self.validated_data.get("extra_data") or {}
        current_extra = instance.extra_data or {}

        if new_extra != current_extra:
            instance.extra_data = new_extra
            instance.save(update_fields=["extra_data"])

        return instance


class AuthWithNonceSerializer(AuthSerializer):
    # Не участвует в сериализации. Нужен для автоматической документации API
    nonce = json_api_serializers.UUIDField(write_only=True)
