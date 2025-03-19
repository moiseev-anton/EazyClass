from rest_framework import serializers
from scheduler.models import Group, Faculty


class FacultieSerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ['id', 'title', 'short_title']


class GroupSerializer(serializers.ModelSerializer):
    faculty = FacultieSerializer()

    class Meta:
        model = Group
        fields = ['id', 'title', 'grade', 'faculty']
