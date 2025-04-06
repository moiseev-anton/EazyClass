from rest_framework import serializers
from scheduler.models import Period, Lesson, Group, Teacher, Subject, Classroom


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "title", "link"]
        read_only_fields = fields


class PeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = Period
        fields = ["id", "lesson_number", "date", "start_time", "end_time"]
        read_only_fields = fields


class TeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ["id", 'full_name', 'short_name']
        read_only_fields = fields


class LessonSerializer(serializers.ModelSerializer):
    group = GroupSerializer()
    teacher = TeacherSerializer()
    subject = serializers.SlugRelatedField(slug_field="title", queryset=Subject.objects.all(), allow_null=True)
    classroom = serializers.SlugRelatedField(slug_field="title", queryset=Classroom.objects.all(), allow_null=True)
    period = PeriodSerializer()

    class Meta:
        model = Lesson
        fields = ["id", "group", "period", "subject", "teacher", "classroom", "subgroup"]
        read_only_fields = fields

