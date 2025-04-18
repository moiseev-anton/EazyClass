from rest_framework_json_api import serializers

from scheduler.models import Group, Faculty


class ShortGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["title"]
        read_only_fields = fields


class CompactGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'title', 'grade', 'link']
        read_only_fields = fields
        resource_name = "group"


class GroupSerializer(serializers.ModelSerializer):
    faculty = serializers.ResourceRelatedField(
        queryset=Faculty.objects.filter(is_active=True),
        required=False
    )

    included_serializers = {
        'faculty': 'scheduler.api.v1.serializers.FacultySerializer',
    }

    class Meta:
        model = Group
        fields = ['id', 'title', 'grade', 'link', 'faculty']
        resource_name = 'group'
