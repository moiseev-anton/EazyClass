from rest_framework_json_api import serializers

from scheduler.models import Lesson, Group, Teacher
from .group_serializers import CompactGroupSerializer
from .teacher_serializers import TeacherSerializer


class LessonSerializer(serializers.ModelSerializer):
    # Денормализованные поля
    date = serializers.DateField(source="period.date", read_only=True)
    number = serializers.IntegerField(source="period.lesson_number", read_only=True)
    start_time = serializers.TimeField(source="period.start_time", read_only=True)
    end_time = serializers.TimeField(source="period.end_time", read_only=True)
    subject = serializers.CharField(source="subject.title", read_only=True)
    classroom = serializers.CharField(source="classroom.title", read_only=True)

    # Связанные ресурсы для included
    group = serializers.ResourceRelatedField(
        queryset=Group.objects.all(), required=False
    )
    teacher = serializers.ResourceRelatedField(
        queryset=Teacher.objects.all(), required=False
    )

    included_serializers = {
        "group": CompactGroupSerializer,
        "teacher": TeacherSerializer,
    }

    class Meta:
        model = Lesson
        fields = [
            "id",
            "date",
            "number",
            "start_time",
            "end_time",
            "subgroup",
            "subject",
            "classroom",
            "group",
            "teacher",
        ]
        resource_name = "lesson"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        format_param = request.query_params.get("filter[format]", "full") if request else "full"

        if format_param == "compact":
            self.fields["group"] = serializers.CharField(source="group.title", read_only=True)
            self.fields["teacher"] = serializers.CharField(source="teacher.short_name", read_only=True)
            self.fields.pop("included_serializers", None)


# class CompactLessonSerializer(serializers.ModelSerializer):
#     group = serializers.CharField(source="group.title", read_only=True)
#     teacher = serializers.CharField(source="teacher.short_name", read_only=True)
#     number = serializers.IntegerField(source="period.lesson_number", read_only=True)
#     date = serializers.DateField(source="period.date", read_only=True)
#     start_time = serializers.TimeField(source="period.start_time", read_only=True)
#     end_time = serializers.TimeField(source="period.end_time", read_only=True)
#     subject = serializers.CharField(source="subject.title", read_only=True)
#     classroom = serializers.CharField(source="classroom.title", read_only=True)
#
#     class Meta:
#         model = Lesson
#         fields = [
#             "id",
#             "date",
#             "number",
#             "start_time",
#             "end_time",
#             "group",
#             "subgroup",
#             "teacher",
#             "subject",
#             "classroom",
#         ]
#         resource_name = "lesson"

