import logging

from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiResponse,
)
from rest_framework.permissions import AllowAny
from rest_framework_json_api.views import ReadOnlyModelViewSet

from scheduler.api.mixins import JsonApiMixin
from scheduler.api.v1.serializers import ClassroomSerializer, FacultySerializer
from scheduler.models import Classroom

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        tags=["Classrooms"],
        summary="Get Classrooms",
        description="Returns a list of classrooms.",
        auth=[],
        responses={
            200: ClassroomSerializer(many=True),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
    retrieve=extend_schema(
        tags=["Classrooms"],
        summary="Get Classroom",
        description="Returns a specific Classroom.",
        auth=[],
        responses={
            200: ClassroomSerializer(many=False),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
)
class ClassroomViewSet(JsonApiMixin, ReadOnlyModelViewSet):
    queryset = Classroom.objects.all()
    serializer_class = ClassroomSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).order_by("title")
