import logging

from django.contrib.contenttypes.models import ContentType
from rest_framework_json_api import serializers as json_api_serializers
from django.utils.module_loading import import_string

from scheduler.models import Subscription

logger = logging.getLogger(__name__)


class SubscriptionSerializer(json_api_serializers.ModelSerializer):
    SUBSCRIPTION_SERIALIZERS = {
        "group": "scheduler.api.v1.serializers.CompactGroupSerializer",
        "teacher": "scheduler.api.v1.serializers.TeacherSerializer",
    }

    object_type = json_api_serializers.ChoiceField(
        choices=list(SUBSCRIPTION_SERIALIZERS.keys()),
        write_only=True,
        help_text="Тип объекта подписки",
    )
    object_id = json_api_serializers.IntegerField(
        min_value=1, write_only=True, help_text="ID объекта для подписки"
    )
    object = json_api_serializers.SerializerMethodField(
        read_only=True, help_text="Сериализованный объект подписки"
    )

    class Meta:
        model = Subscription
        fields = ("id", "object_type", "object_id", "object")
        read_only_fields = ("id", "object")
        resource_name = "subscription"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Лениво загружаем сериализаторы при первом использовании
        self._model_serializers = {
            model: import_string(path)
            for model, path in self.SUBSCRIPTION_SERIALIZERS.items()
        }

    def get_object(self, obj):
        """Сериализует подписанный объект (группу/учителя)"""
        if not obj.content_object:
            return None

        model_name = obj.content_type.model
        serializer_class = self._model_serializers.get(model_name)
        if not serializer_class:
            return None
        # return serializer(obj.content_object, context=self.context).data
        serializer = serializer_class(obj.content_object, context=self.context)
        serialized_data = serializer.data
        logger.info(serialized_data)
        return {
            "type": model_name,
            "id": str(serialized_data.pop("id")),
            "attributes": serialized_data
        }

    def validate(self, attrs):
        """Проверка существования объекта и допустимости типа"""
        validated_data = super().validate(attrs)
        object_type = validated_data.get("object_type")
        object_id = validated_data.get("object_id")

        content_type = ContentType.objects.filter(
            app_label="scheduler", model=object_type
        ).first()
        if not content_type:
            raise json_api_serializers.ValidationError(
                {"object_type": f"Invalid subscription type: {object_type}"}
            )

        model_class = content_type.model_class()
        if not model_class.objects.filter(id=object_id, is_active=True).exists():
            raise json_api_serializers.ValidationError(
                {"object_id": f"Active {object_type} with id {object_id} does not exist"}
            )

        validated_data["content_type"] = content_type
        return validated_data

    def create(self, validated_data):
        """Создание подписки"""
        return Subscription.objects.create(
            user=self.context["request"].user,
            content_type=validated_data["content_type"],
            object_id=validated_data["object_id"],
        )

    def update(self, instance, validated_data):
        instance.content_type = validated_data["content_type"]
        instance.object_id = validated_data["object_id"]
        instance.save()
        return instance

