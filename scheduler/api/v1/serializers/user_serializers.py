from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import User


class UserSerializer(json_api_serializers.ModelSerializer):

    # included_serializers = {
    #     "accounts": "scheduler.api.v1.serializers.SocialAccountSerializer",
    #     "subscriptions": "scheduler.api.v1.serializers.SubscriptionSerializer",
    # }

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "notify_schedule_updates",
            "notify_upcoming_lessons",
            "accounts",
            "subscriptions",
        )
        read_only_fields = ("id", "accounts", "subscriptions")
        resource_name = "users"
