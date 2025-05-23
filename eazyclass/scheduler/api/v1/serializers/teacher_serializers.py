from rest_framework_json_api import serializers

from scheduler.models import Teacher


# TODO: Избавиться, заменить на teacher = serializers.CharField(source="teacher.short_name", read_only=True)
class CompactTeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ["short_name"]
        read_only_fields = fields


class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ["id", "full_name", "short_name"]
        read_only_fields = fields
        resource_name = "teacher"
