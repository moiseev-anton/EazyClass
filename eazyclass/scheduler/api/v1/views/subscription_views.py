from django.db import IntegrityError
from drf_spectacular.utils import OpenApiResponse, OpenApiExample, extend_schema
from rest_framework import status, mixins
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from scheduler.api.response_examples import SubscriptionSuccessResponse
from scheduler.api.v1.serializers import SubscriptionSerializer
from scheduler.api.v1.views.mixins import JsonApiViewMixin
from scheduler.models import Subscription
from rest_framework import exceptions


class SubscriptionAlreadyExists(exceptions.APIException):
    status_code = 409
    default_detail = ("User already has a subscription."
                      " Use PATCH /subscriptions/me/ to replace it.")
    default_code = "subscription_conflict"


class SubscriptionViewSet(
    JsonApiViewMixin,
    mixins.CreateModelMixin,
    GenericViewSet
):
    permission_classes = [IsAuthenticated]
    serializer_class = SubscriptionSerializer
    queryset = Subscription.objects.all()
    resource_name = "subscription"
    filter_backends = []

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Create subscription",
        auth=[],
        request=SubscriptionSerializer,
        responses={
            201: SubscriptionSuccessResponse,
            409: OpenApiResponse(description="Conflict"),
            400: OpenApiResponse(description="Invalid input"),
        },
        description="Create a new subscription. Only one subscription per user is allowed."
    )
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            self.perform_create(serializer)
        except IntegrityError:
            raise SubscriptionAlreadyExists()

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    @extend_schema(
        tags=["Subscriptions"],
        summary="Get my subscription",
        operation_id="subscriptions_me",
        auth=[],
        # methods=["GET"],
        responses={
            200: SubscriptionSuccessResponse,
            404: OpenApiResponse(description="No subscription found"),
        },
        description="Retrieve the current subscription of the authenticated user."
    )
    @extend_schema(
        tags=["Subscriptions"],
        summary="Update my subscription",
        methods=["PATCH"],
        auth=[],
        request=SubscriptionSerializer,
        responses={
            200: SubscriptionSuccessResponse,
            404: OpenApiResponse(description="No subscription found"),
            400: OpenApiResponse(description="Invalid input"),
        },
        description="Update the current subscription of the authenticated user."
    )
    @extend_schema(
        tags=["Subscriptions"],
        summary="Delete my subscription",
        methods=["DELETE"],
        auth=[],
        responses={
            204: OpenApiResponse(description="Subscription deleted successfully"),
            404: OpenApiResponse(description="No subscription found"),
        },
        description="Delete the current subscription of the authenticated user."
    )
    @action(detail=False, methods=["GET", "PATCH", "DELETE"], url_path="me")
    def manage_own_subscription(self, request):
        """Получить текущую подписку"""
        instance = self.get_queryset().first()
        self.kwargs["pk"] = str(instance.pk)

        if request.method == "GET":
            if not instance:
                raise exceptions.NotFound("No subscription found for this user")
            serializer = self.get_serializer(instance)
            return Response(serializer.data)

        elif request.method == "PATCH":
            if not instance:
                raise exceptions.NotFound("No subscription found for this user")
            serializer = self.get_serializer(instance, data=request.data, partial=False)
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)

        elif request.method == "DELETE":
            if not instance:
                raise exceptions.NotFound("No subscription found for this user")
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
