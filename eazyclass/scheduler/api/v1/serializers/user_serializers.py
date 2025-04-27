from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import SocialAccount, User


class SocialAccountSerializer(json_api_serializers.ModelSerializer):
    class Meta:
        model = SocialAccount
        fields = ['id', 'platform', 'social_id', 'extra_data']
        resource_name = "social-account"


class UserSerializer(json_api_serializers.ModelSerializer):
    accounts = json_api_serializers.ResourceRelatedField(
        many=True, read_only=True
    )

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'accounts']
        resource_name = "user"

    included_serializers = {
        "accounts": SocialAccountSerializer,
    }


class UserUpdateSerializer(json_api_serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name']
        resource_name = "user"

