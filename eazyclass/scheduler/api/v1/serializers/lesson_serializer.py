from rest_framework import serializers

from scheduler.models import Period, Lesson, Subject, Classroom
from .teacher_serializers import TeacherSerializer


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = ["lesson_number", "date", "start_time", "end_time"]
        read_only_fields = fields


class LessonSerializer(serializers.ModelSerializer):
    group = serializers.SlugRelatedField(
        slug_field="title", queryset=Subject.objects.all(), allow_null=True
    )
    subject = serializers.SlugRelatedField(
        slug_field="title", queryset=Subject.objects.all(), allow_null=True
    )
    classroom = serializers.SlugRelatedField(
        slug_field="title", queryset=Classroom.objects.all(), allow_null=True
    )
    period = PeriodSerializer()
    teacher = TeacherSerializer()

    class Meta:
        model = Lesson
        fields = ["period", "group", "subgroup", "subject", "classroom", "teacher"]
        read_only_fields = fields
