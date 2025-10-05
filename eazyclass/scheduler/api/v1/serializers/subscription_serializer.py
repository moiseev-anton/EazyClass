import logging

from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import Subscription
from scheduler.models import (
    TeacherSubscription,
    Teacher,
    GroupSubscription,
    Group,
)

logger = logging.getLogger(__name__)


class BaseSubscriptionSerializer(json_api_serializers.ModelSerializer):
    user = json_api_serializers.ResourceRelatedField(read_only=True)
    included_serializers = {
        "user": "scheduler.api.v1.serializers.UserSerializer",
        "group": "scheduler.api.v1.serializers.GroupSerializer",
        "teacher": "scheduler.api.v1.serializers.TeacherSerializer",
    }

    class Meta:
        resource_name = "subscriptions"
        read_only_fields = ["created_at", "updated_at"]
        exclude = ("polymorphic_ctype",)


class TeacherSubscriptionSerializer(BaseSubscriptionSerializer):
    teacher = json_api_serializers.ResourceRelatedField(queryset=Teacher.objects.all())

    class Meta(BaseSubscriptionSerializer.Meta):
        model = TeacherSubscription
        resource_name = "teacher-subscriptions"


class GroupSubscriptionSerializer(BaseSubscriptionSerializer):
    group = json_api_serializers.ResourceRelatedField(queryset=Group.objects.all())

    class Meta(BaseSubscriptionSerializer.Meta):
        model = GroupSubscription
        resource_name = "group-subscriptions"


class SubscriptionSerializer(json_api_serializers.PolymorphicModelSerializer):

    polymorphic_serializers = [
        TeacherSubscriptionSerializer,
        GroupSubscriptionSerializer,
    ]

    included_serializers = {
        "user": "scheduler.api.v1.serializers.UserSerializer",
        "group": "scheduler.api.v1.serializers.GroupSerializer",
        "teacher": "scheduler.api.v1.serializers.TeacherSerializer",
    }

    class Meta:
        model = Subscription
        exclude = ("polymorphic_ctype",)
        read_only_fields = ["created_at", "updated_at"]
        resource_name = "subscriptions"
