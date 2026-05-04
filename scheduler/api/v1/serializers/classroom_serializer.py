from rest_framework_json_api import serializers as json_api_serializers

from scheduler.models import Classroom

class ClassroomSerializer(json_api_serializers.ModelSerializer):
    class Meta:
        model = Classroom
        fields = ["id", "title"]