from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import Faculty


class FacultySerializer(json_api_serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ["id", "title", "short_title"]
