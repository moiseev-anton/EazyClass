from rest_framework import serializers
from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import Platform


class DeeplinkParamsSerializer(serializers.Serializer):
    platform = json_api_serializers.ChoiceField(choices=Platform.choices, required=True)


class DeeplinkOutputSerializer(serializers.Serializer):
    deeplink = json_api_serializers.URLField()
    nonce = json_api_serializers.UUIDField()

    class Meta:
        resource_name = "deeplink"
