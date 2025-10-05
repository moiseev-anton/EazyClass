import logging

from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiResponse,
)
from rest_framework.permissions import AllowAny
from rest_framework_json_api.views import ReadOnlyModelViewSet

from scheduler.api.mixins import JsonApiMixin
from scheduler.api.v1.serializers import FacultySerializer
from scheduler.models import Faculty

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        tags=["Faculties"],
        summary="Get Faculties",
        description="Returns a list of faculties.",
        auth=[],
        responses={
            200: FacultySerializer(many=True),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
    retrieve=extend_schema(
        tags=["Faculties"],
        summary="Get Faculty",
        description="Returns a specific Faculty.",
        auth=[],
        responses={
            200: FacultySerializer(many=False),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
)
class FacultyViewSet(JsonApiMixin, ReadOnlyModelViewSet):
    queryset = Faculty.objects.all()
    serializer_class = FacultySerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).order_by("title")
