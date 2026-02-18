import logging

from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework import mixins
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import GenericViewSet

from scheduler.api.filters import SubscriptionFilter
from scheduler.api.viewsets import ReadOnlyModelViewSet

from scheduler.api.mixins import JsonApiMixin
from scheduler.api.v1.serializers import (
    SubscriptionSerializer,
    GroupSubscriptionSerializer,
    TeacherSubscriptionSerializer,
)
from scheduler.models import Subscription, GroupSubscription, TeacherSubscription

logger = logging.getLogger(__name__)


class GroupSubscriptionViewSet(
    JsonApiMixin,
    mixins.CreateModelMixin,  # POST
    # mixins.UpdateModelMixin,  # PATCH
    mixins.DestroyModelMixin,  # DELETE
    GenericViewSet,  # Базовый
):
    queryset = GroupSubscription.objects.all().order_by("pk")
    serializer_class = GroupSubscriptionSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "patch", "delete"]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Create a group subscription",
        description="Create a group subscription for the current user",
        request=GroupSubscriptionSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    # @extend_schema(
    #     tags=["Subscriptions"],
    #     summary="Update a group subscription",
    #     description="Update a group subscription for the current user",
    #     request=GroupSubscriptionSerializer,
    # )
    # def partial_update(self, request, *args, **kwargs):
    #     return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Delete a group subscription",
        description="Delete a group subscription for the current user",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class TeacherSubscriptionViewSet(
    JsonApiMixin,
    mixins.CreateModelMixin,  # POST
    # mixins.UpdateModelMixin,  # PATCH
    mixins.DestroyModelMixin,  # DELETE
    GenericViewSet,  # Базовый
):
    queryset = TeacherSubscription.objects.all().order_by("pk")
    permission_classes = [IsAuthenticated]
    serializer_class = TeacherSubscriptionSerializer
    http_method_names = ["post", "patch", "delete"]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Create a teacher subscription",
        description="Create a group teacher for the current user",
        request=TeacherSubscriptionSerializer,
    )
    def create(self, request, *args, **kwargs):
        return super().create(request, *args, **kwargs)

    # @extend_schema(
    #     tags=["Subscriptions"],
    #     summary="Update a teacher subscription",
    #     description="Update a teacher subscription for the current user",
    #     request=TeacherSubscriptionSerializer,
    # )
    # def partial_update(self, request, *args, **kwargs):
    #     return super().partial_update(request, *args, **kwargs)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Delete a teacher subscription",
        description="Delete a teacher subscription for the current user",
    )
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)


class SubscriptionAlreadyExists(exceptions.APIException):
    # Не используется. При создании новой подписки автоматическое удаление старых
    status_code = 409
    default_detail = (
        "User already has a subscription."
        " Use PATCH /subscriptions/me/ to replace it."
    )
    default_code = "subscription_conflict"


class SubscriptionViewSet(
    JsonApiMixin,
    ReadOnlyModelViewSet,
):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionSerializer
    filterset_class = SubscriptionFilter
    queryset = Subscription.objects.all()

    http_method_names = ["get"]

    select_for_includes = {
        "__all__": [],
        "group": ["group"],
        "teacher": ["teacher"],
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.filter(user=self.request.user)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Get subscriptions",
        description="Get all subscriptions for the current user",
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Get subscription",
        description="Get a subscription for the current user",
    )
    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)
