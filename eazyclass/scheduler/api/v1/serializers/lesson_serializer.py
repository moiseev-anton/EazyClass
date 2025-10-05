from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import Lesson, Group, Teacher
from .group_serializers import GroupSerializer
from .teacher_serializers import TeacherSerializer


class LessonSerializer(json_api_serializers.ModelSerializer):
    """Сериализатор для уроков, предоставляющий информацию о расписании занятий."""

    date = json_api_serializers.DateField(
        source="period.date",
        read_only=True,
    )
    number = json_api_serializers.IntegerField(
        source="period.lesson_number", read_only=True
    )
    start_time = json_api_serializers.TimeField(
        source="period.start_time",
        read_only=True,
    )
    end_time = json_api_serializers.TimeField(source="period.end_time", read_only=True)
    subject = json_api_serializers.CharField(source="subject.title", read_only=True)
    classroom = json_api_serializers.CharField(source="classroom.title", read_only=True)
    group = json_api_serializers.ResourceRelatedField(queryset=Group.objects.all())
    teacher = json_api_serializers.ResourceRelatedField(queryset=Teacher.objects.all())

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
        resource_name = "lessons"

    included_serializers = {
        "group": GroupSerializer,
        "teacher": TeacherSerializer,
    }
