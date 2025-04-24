from rest_framework_json_api import serializers

from scheduler.models import Lesson, Group, Teacher
from .group_serializers import CompactGroupSerializer
from .teacher_serializers import TeacherSerializer


class LessonSerializer(serializers.ModelSerializer):
    """Сериализатор для уроков, предоставляющий информацию о расписании занятий."""

    date = serializers.DateField(
        source="period.date",
        read_only=True,
    )
    number = serializers.IntegerField(source="period.lesson_number", read_only=True)
    start_time = serializers.TimeField(
        source="period.start_time",
        read_only=True,
    )
    end_time = serializers.TimeField(source="period.end_time", read_only=True)
    subject = serializers.CharField(source="subject.title", read_only=True)
    classroom = serializers.CharField(source="classroom.title", read_only=True)
    group = serializers.ResourceRelatedField(queryset=Group.objects.all())
    teacher = serializers.ResourceRelatedField(queryset=Teacher.objects.all())

    class Meta:
        model = Lesson
        fields = [
            "id",
            "date",
            "number",
            "start_time",
            "end_time",
            "subject",
            "classroom",
            "subgroup",
            "group",
            "teacher",
        ]
        resource_name = "lesson"

    included_serializers = {
        "group": CompactGroupSerializer,
        "teacher": TeacherSerializer,
    }
