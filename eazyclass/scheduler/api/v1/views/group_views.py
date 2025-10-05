import logging

from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
)
from rest_framework.permissions import AllowAny

from scheduler.api.filters import GroupFilter
from scheduler.api.mixins import JsonApiMixin
from scheduler.api.v1.serializers import GroupSerializer
from scheduler.api.viewsets import ReadOnlyModelViewSet
from scheduler.models import Group

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        tags=["Groups"],
        summary="Get Groups",
        description="Returns a list of groups.",
        parameters=[
            OpenApiParameter(name="filter[search]", exclude=True),
        ],
        auth=[],
        responses={
            200: GroupSerializer(many=True),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
    retrieve=extend_schema(
        tags=["Groups"],
        summary="Get Group",
        description="Returns a specific group.",
        auth=[],
        responses={
            200: GroupSerializer(many=False),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
)
class GroupViewSet(
    JsonApiMixin,
    ReadOnlyModelViewSet,
):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    filterset_class = GroupFilter
    permission_classes = [AllowAny]
    resource_name = "groups"

    select_for_includes = {
        "__all__": [],
        "faculty": ["faculty"],
    }

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).order_by("title")
