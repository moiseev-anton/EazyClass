from collections import defaultdict

from rest_framework import serializers

from scheduler.models import Group, Faculty


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
