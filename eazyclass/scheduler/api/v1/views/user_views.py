import logging

from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api.views import (
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
)

from scheduler.api.mixins import JsonApiMixin
from scheduler.api.v1.serializers import UserSerializer
from scheduler.models import User

logger = logging.getLogger(__name__)


class UserViewSet(
    JsonApiMixin,
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    # select_for_includes = {
    #     "__all__": [],
    #     "accounts": ["accounts"],
    # }

    prefetch_for_includes = {
        "__all__": [],
        "subscriptions": ["subscriptions"],
        "accounts": ["accounts"],
    }

    def get_queryset(self):
        return self.queryset.filter(is_active=True)

    @extend_schema(
        tags=["User"],
        methods=["GET"],
        summary="Get current user",
        description="Retrieve the authenticated user’s profile.",
        responses={200: OpenApiResponse(UserSerializer(many=True))},
    )
    @extend_schema(
        tags=["User"],
        methods=["PATCH"],
        summary="Update current user",
        description="Update user profile (username, first_name, last_name).",
        request=UserSerializer,
        responses={200: OpenApiResponse(UserSerializer(many=True))},
    )
    # @extend_schema(
    #     tags=['User'],
    #     methods=['DELETE'],
    #     summary="Deactivate current user",
    #     description='Deactivate user account instead of deleting.',
    #     responses={204: None}
    # )
    @action(detail=False, methods=["get", "patch"], url_path="me")
    def me(self, request):
        try:
            self.kwargs["pk"] = request.user.pk

            if request.method == "GET":
                serializer = self.get_serializer(request.user)
                return Response(serializer.data)

            elif request.method == "PATCH":
                serializer = self.get_serializer(
                    request.user, data=request.data, partial=True
                )
                serializer.is_valid(raise_exception=True)
                serializer.save()
                logger.info(f"User {request.user.id} updated profile")
                return Response(serializer.data)
        except Exception as e:
            logger.error(e)
            raise

        # elif request.method == "DELETE":
        #     request.user.is_active = False
        #     request.user.save()
        #     return Response(status=status.HTTP_204_NO_CONTENT)
