import logging

from drf_spectacular.utils import (
    extend_schema_view,
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
)
from rest_framework import status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_json_api.views import (
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
)

from scheduler.api.filters import GroupFilter
from scheduler.api.v1.serializers import GroupSerializer
from scheduler.api.v1.views.mixins import JsonApiMixin, EtagMixin
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
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
    EtagMixin,
    viewsets.ReadOnlyModelViewSet,
):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    filterset_class = GroupFilter
    permission_classes = [AllowAny]
    resource_name = "group"

    select_for_includes = {
        "__all__": [],
        "faculty": ["faculty"],
    }

    def get_queryset(self):
        return super().get_queryset().filter(is_active=True).order_by("title")

    def list(self, request, *args, **kwargs):
        etag, is_matched = self.check_etag(many=True)
        if is_matched:
            return Response(status=status.HTTP_304_NOT_MODIFIED)
        response = super().list(request, *args, **kwargs)
        if response.status_code == 200:
            response["ETag"] = f'"{etag}"'
        return response

    def retrieve(self, request, *args, **kwargs):
        etag, is_matched = self.check_etag()
        if is_matched:
            return Response(status=status.HTTP_304_NOT_MODIFIED)
        response = super().retrieve(request, *args, **kwargs)
        if response.status_code == 200:
            response["ETag"] = etag
        return response
