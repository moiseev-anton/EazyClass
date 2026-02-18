import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework_json_api.views import (
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
)

from scheduler.api.mixins import ETagMixin, ETagRetrieveModelMixin, JsonApiMixin
from scheduler.api.permissions import IsSelf
from scheduler.api.v1.serializers import UserSerializer
from scheduler.models import User

logger = logging.getLogger(__name__)


class UserViewSet(
    JsonApiMixin,
    ETagMixin,
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    # RelatedMixin,
    ETagRetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    Представление для работы с пользователями.
    Поддерживает получение и частичное обновление текущего пользователя.
    """

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsSelf]
    http_method_names = ["get", "patch"]

    queryset = User.objects.filter(is_active=True)

    @extend_schema(
        tags=["User"],
        summary="Get user (self only)",
        description="Retrieve your own user profile.",
        responses={200: OpenApiResponse(UserSerializer)},
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @extend_schema(
        tags=["User"],
        summary="Update user (self only)",
        description="Update your own user profile (username, first_name, last_name, subscriptions).",
        request=UserSerializer,
        responses={200: OpenApiResponse(UserSerializer)},
    )
    def partial_update(self, request, *args, **kwargs):
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        tags=["User"],
        methods=["GET"],
        summary="Get current user",
        description="Retrieve the authenticated user’s profile.",
        responses={200: OpenApiResponse(UserSerializer(many=False))},
    )
    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request, *args, **kwargs):
        self.kwargs[self.lookup_field] = request.user.pk
        return self.retrieve(request, *args, **kwargs)
