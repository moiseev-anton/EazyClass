from collections import defaultdict

from rest_framework_json_api import serializers

from scheduler.models import Group, Faculty, Teacher


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'title', 'link']
        read_only_fields = fields


class BotFacultyMapSerializer(serializers.Serializer):
    def to_representation(self, data):
        # Преобразуем queryset в словарь с ключами по id
        return {faculty.id: BotFacultySerializer(faculty).data for faculty in data}


class BotFacultySerializer(serializers.ModelSerializer):
    courses = serializers.SerializerMethodField()

    class Meta:
        model = Faculty
        fields = ['id', 'title', 'short_title', 'courses']
        read_only_fields = fields

    def get_courses(self, faculty):
        """ Формирование структуры курсов с группами """
        courses = defaultdict(dict)
        groups = getattr(faculty, 'active_groups', [])
        for group in groups:
            grade = str(group.grade)
            group_data = GroupSerializer(group).data
            courses[grade][group.id] = group_data
        return courses


class BotTeacherSerializer(serializers.ModelSerializer):
    class Meta:
        model = Teacher
        fields = ['id', 'full_name', 'short_name']
        read_only_fields = fields


class BotTeacherMapSerializer(serializers.Serializer):
    def to_representation(self, data):
        """
        Преобразует queryset учителей в словарь, где ключи — первые буквы фамилий,
        а значения — списки учителей, отсортированные по full_name.
        """
        teachers_map = defaultdict(dict)
        for teacher in data:
            first_letter = teacher.full_name[0].upper()
            teachers_map[first_letter][teacher.id] = BotTeacherSerializer(teacher).data

        return teachers_map
