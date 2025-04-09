from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from scheduler.api.v1.serializers.group_serializers import CompactGroupSerializer
from scheduler.api.v1.serializers.teacher_serializers import CompactTeacherSerializer
from scheduler.models import Subscription


class SubscriptionSerializer(serializers.ModelSerializer):
    SUBSCRIPTION_MODELS = {
        "group": CompactGroupSerializer,
        "teacher": CompactTeacherSerializer,
    }

    content_type = serializers.SlugRelatedField(
        slug_field="model",
        queryset=ContentType.objects.filter(
            app_label="scheduler", model__in=SUBSCRIPTION_MODELS.keys()
        ),
    )
    object_id = serializers.IntegerField()
    object = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Subscription
        fields = ["id", "content_type", "object_id", "object"]
        read_only_fields = ["user"]

    def get_object(self, obj):
        if not obj.content_object:
            return None

        model_name = obj.content_type.model
        serializer_class = self.SUBSCRIPTION_MODELS.get(model_name)

        if not serializer_class:
            return str(obj.content_object)

        return serializer_class(obj.content_object).data

    def validate(self, data):
        """Проверка существования объекта и разрешенных типов."""
        content_type = data["content_type"]
        object_id = data["object_id"]
        model_class = content_type.model_class()
        if not model_class.objects.filter(id=object_id).exists():
            raise serializers.ValidationError(
                {"detail": f"Объект не найден или недоступен"}
            )
        return data
