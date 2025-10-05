from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import Group, Faculty


class GroupSerializer(json_api_serializers.ModelSerializer):
    faculty = json_api_serializers.ResourceRelatedField(
        queryset=Faculty.objects.filter(is_active=True), required=False
    )

    included_serializers = {
        "faculty": "scheduler.api.v1.serializers.FacultySerializer",
    }

    class Meta:
        model = Group
        fields = ["id", "title", "grade", "link", "faculty"]
        resource_name = "groups"
