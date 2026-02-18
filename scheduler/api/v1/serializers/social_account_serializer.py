from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import SocialAccount


class SocialAccountSerializer(json_api_serializers.ModelSerializer):
    included_serializers = {
        "user": "scheduler.api.v1.serializers.UserSerializer",
    }

    class Meta:
        model = SocialAccount
        resource_name = "social-accounts"
        fields = ("id", "platform", "social_id", "chat_id", "is_blocked", "extra_data", "user")
        read_only_fields = ("id", "platform", "social_id")


class SocialAccountAuthSerializer(SocialAccountSerializer):
    created = json_api_serializers.SerializerMethodField(read_only=True)

    class Meta(SocialAccountSerializer.Meta):
        meta_fields = ("created",)

    def get_created(self, obj):
        return self.context.get("created", False)


class SocialAccountAuthWithNonceSerializer(SocialAccountAuthSerializer):
    nonce_status = json_api_serializers.SerializerMethodField(read_only=True)

    class Meta(SocialAccountAuthSerializer.Meta):
        meta_fields = ("created", "nonce_status")

    def get_nonce_status(self, obj):
        # Изначально будет None, потом вручную добавим результат вызова NonceView.post() в данные ответа.
        # Этот метод нужен чтобы не ругался DRF. Рендерер на основании meta_fields сформирует meta ресурса.
        ...
