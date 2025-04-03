from collections import defaultdict

from rest_framework import serializers

from scheduler.models import Group, Faculty, Teacher


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ['id', 'title', 'link']
        read_only_fields = fields


class BotFacultyMapSerializer(serializers.Serializer):
    def to_representation(self, data):
        # Преобразуем queryset в словарь с ключами по id
        return {str(faculty.id): BotFacultySerializer(faculty).data
                for faculty in data}


class BotFacultySerializer(serializers.ModelSerializer):
    courses = serializers.SerializerMethodField()

    class Meta:
        model = Faculty
        fields = ['id', 'title', 'short_title', 'courses']
        read_only_fields = fields

    def get_courses(self, faculty):
        """ Формирование структуры курсов с группами """
        courses = defaultdict(list)
        groups = getattr(faculty, 'active_groups', [])
        for group in groups:
            courses[group.grade].append(GroupSerializer(group).data)
        return dict(sorted(courses.items(), key=lambda x: x[0]))


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
        teachers_map = {}
        for teacher in data:
            first_letter = teacher.full_name[0].upper()  # Берем первую букву и приводим к верхнему регистру
            if first_letter not in teachers_map:
                teachers_map[first_letter] = []
            teachers_map[first_letter].append(BotTeacherSerializer(teacher).data)

        # Сортируем списки учителей внутри каждого ключа
        for letter in teachers_map:
            teachers_map[letter].sort(key=lambda x: x['full_name'])

        return teachers_map
