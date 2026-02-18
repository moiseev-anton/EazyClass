from rest_framework import serializers
from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models.social_account_model import Platform


class DeeplinkParamsSerializer(serializers.Serializer):
    platform = json_api_serializers.ChoiceField(choices=Platform.choices, required=True)


class DeeplinkOutputSerializer(serializers.Serializer):
    platform = serializers.CharField()
    deeplink = serializers.URLField()
    nonce = serializers.UUIDField()
    bot_url = serializers.URLField()
    bot_username = serializers.CharField()
