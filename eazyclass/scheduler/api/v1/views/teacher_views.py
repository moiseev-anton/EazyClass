import logging

from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
)
from rest_framework.permissions import AllowAny
from rest_framework_json_api.views import ReadOnlyModelViewSet

from scheduler.api.filters import TeacherFilter
from scheduler.api.v1.serializers import TeacherSerializer
from scheduler.api.v1.views.mixins import JsonApiViewMixin
from scheduler.models import Teacher

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        tags=["Teachers"],
        summary="Get Teachers",
        description="Returns a list of teachers.",
        parameters=[
            OpenApiParameter(name="filter[search]", exclude=True),
        ],
        auth=[],
        responses={
            200: TeacherSerializer(many=True),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
    retrieve=extend_schema(
        tags=["Teachers"],
        summary="Get Teacher",
        description="Returns a specific teacher.",
        auth=[],
        responses={
            200: TeacherSerializer(many=False),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
)
class TeacherViewSet(JsonApiViewMixin, ReadOnlyModelViewSet):
    queryset = Teacher.objects.all()
    serializer_class = TeacherSerializer
    permission_classes = [AllowAny]
    filterset_class = TeacherFilter
    resource_name = "teacher"

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).order_by("full_name")
