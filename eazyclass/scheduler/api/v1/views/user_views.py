import logging

from drf_spectacular.utils import extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_json_api.views import (
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
)

from scheduler.models import User
from ..serializers import UserSerializer, UserUpdateSerializer

logger = logging.getLogger(__name__)


class UserViewSet(
    AutoPrefetchMixin,
    PreloadIncludesMixin,
    RelatedMixin,
    viewsets.GenericViewSet,
):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]

    select_for_includes = {
        "__all__": [],
        "accounts": ["accounts"],
    }

    def get_queryset(self):
        return self.queryset.filter(is_active=True)

    def get_serializer_class(self):
        if self.action in ["me"] and self.request.method in ("PATCH", "PUT"):
            return UserUpdateSerializer
        return UserSerializer

    @extend_schema(
        tags=['User'],
        methods=['GET'],
        summary="Get current user",
        description='Retrieve the authenticated user’s profile.',
        responses={200: UserSerializer},
    )
    @extend_schema(
        tags=['User'],
        methods=['PATCH'],
        summary="Update current user",
        description='Update user profile (username, first_name, last_name).',
        request=UserUpdateSerializer,
        responses={200: UserSerializer}
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
        self.kwargs['pk'] = request.user.pk

        if request.method == "GET":
            serializer = self.get_serializer(request.user)
            return Response(serializer.data)

        elif request.method == "PATCH":
            serializer = self.get_serializer(
                request.user,
                data=request.data,
                partial=True
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            logger.info(f"User {request.user.id} updated profile")
            return Response(serializer.data)

        # elif request.method == "DELETE":
        #     request.user.is_active = False
        #     request.user.save()
        #     return Response(status=status.HTTP_204_NO_CONTENT)
