from rest_framework import serializers

from scheduler.models import Group


class CompactGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["title"]
        read_only_fields = fields


class GroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = Group
        fields = ["id", "title", "link"]
        read_only_fields = fields
