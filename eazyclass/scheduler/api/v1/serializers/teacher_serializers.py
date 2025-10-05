from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import Teacher


class TeacherSerializer(json_api_serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ["id", "full_name", "short_name"]
        read_only_fields = fields
