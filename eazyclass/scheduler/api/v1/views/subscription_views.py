from django.db import IntegrityError
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from scheduler.api.permissions import IsOwner
from scheduler.api.v1.serializers import SubscriptionSerializer
from scheduler.api.v1.views.mixins import JsonApiViewMixin
from scheduler.models import Subscription


class SubscriptionViewSet(JsonApiViewMixin, ModelViewSet):
    serializer_class = SubscriptionSerializer
    permission_classes = [IsAuthenticated, IsOwner]
    lookup_field = "id"
    resource_name = "subscription"

    def get_queryset(self):
        """Возвращает только подписки текущего пользователя."""
        return (
            Subscription.objects.filter(user=self.request.user)
            .select_related("content_type")
            .prefetch_related("content_object")
        )

    def perform_create(self, serializer):
        """Создание подписки с обработкой ограничения на одну."""
        try:
            serializer.save(user=self.request.user)
        except IntegrityError:
            raise ValidationError(
                {
                    "detail": "У вас уже есть подписка. "
                    "Используйте PUT/PATCH для обновления или DELETE для удаления."
                }
            )

    @action(detail=False, methods=["get"], url_path="current")
    def get_current(self, request):
        """Получение текущей подписки (удобно при ограничении на одну)."""
        subscription = self.get_queryset().first()
        if not subscription:
            return Response(
                {"detail": "Подписка не найдена"}, status=status.HTTP_404_NOT_FOUND
            )
        serializer = self.get_serializer(subscription)
        return Response(serializer.data)
