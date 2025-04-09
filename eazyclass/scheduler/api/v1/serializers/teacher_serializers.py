from rest_framework import serializers

from scheduler.models import Teacher


class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ["id", "full_name", "short_name"]
        read_only_fields = fields


class CompactTeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ["short_name"]
        read_only_fields = fields
