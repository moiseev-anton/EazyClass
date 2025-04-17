from rest_framework_json_api import serializers

from scheduler.models import Teacher


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

    # def to_representation(self, instance):
    #     return {
    #         "id": instance.id,
    #         "type": "teacher",
    #         "attributes": {
    #             "short_name": instance.short_name,
    #             "full_name": instance.full_name,
    #         },
    #     }
