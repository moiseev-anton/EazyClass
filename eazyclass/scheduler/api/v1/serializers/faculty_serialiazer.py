from rest_framework_json_api import serializers

from scheduler.models import Faculty


class FacultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ["id", "title", "short_title"]
        resource_name = "faculty"
