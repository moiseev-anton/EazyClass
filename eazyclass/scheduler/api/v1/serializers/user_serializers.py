from django.utils import timezone
from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import SocialAccount, User


class SocialAccountSerializer(json_api_serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = ["id", "platform", "social_id", "extra_data"]
        resource_name = "social-account"


class UserSerializer(json_api_serializers.ModelSerializer):
    accounts = json_api_serializers.ResourceRelatedField(many=True, read_only=True)

    class Meta:
        model = User
        fields = ["id", "username", "first_name", "last_name", "accounts"]
        resource_name = "user"

    included_serializers = {
        "accounts": SocialAccountSerializer,
    }


class UserUpdateSerializer(json_api_serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["username", "first_name", "last_name"]
        resource_name = "user"


class UserOutputSerializer(json_api_serializers.ModelSerializer):
    created = json_api_serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "first_name", "last_name", "username")
        resource_name = "user"
        meta_fields = ("created",)

    def get_created(self, obj):
        return self.context.get("created", False)


class UserOutputWithNonceSerializer(UserOutputSerializer):
    nonce_status = json_api_serializers.SerializerMethodField()

    class Meta(UserOutputSerializer.Meta):
        meta_fields = ("created", "nonce_status")

    def get_nonce_status(self, obj):
        # Пока None, потом подставим актуальный после вызова NonceView вручную
        # этот метод нужен чтобы не ругался DRF, рендерер на основании meta_fields сам сформирует meta ресурса
        return self.context.get("nonce_status")
