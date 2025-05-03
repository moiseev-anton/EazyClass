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
    created: bool

    @property
    def status_code(self) -> int:
        return status.HTTP_201_CREATED if self.created else status.HTTP_200_OK


class RegisterSerializer(json_api_serializers.Serializer):
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
        resource_name = "user"

    def create(self, validated_data) -> AuthResult:
        user, created = User.objects.get_or_create_user(
            social_id=validated_data["social_id"],
            platform=validated_data["platform"],
            first_name=validated_data.get("first_name") or "",
            last_name=validated_data.get("last_name") or "",
            extra_data=validated_data.get("extra_data") or {},
        )
        return AuthResult(user=user, created=created)

    def save(self, **kwargs) -> AuthResult:
        """Save and return AuthResult with user instance and creation flag."""
        return self.create(self.validated_data)


class RegisterWithNonceSerializer(RegisterSerializer):
    nonce = json_api_serializers.UUIDField()
