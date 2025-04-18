import logging

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.viewsets import ModelViewSet

from scheduler.api.filters import LessonFilter
from scheduler.api.permissions import IsAdminOrReadOnly
from scheduler.api.v1.serializers import LessonSerializer
from scheduler.models import Lesson, Subscription, Group, Teacher

logger = logging.getLogger(__name__)


class LessonViewSet(ModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
    filterset_class = LessonFilter
    permission_classes = [IsAdminOrReadOnly]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("group", "teacher", "subject", "classroom", "period")
            .order_by("period__date", "period__lesson_number", "subgroup")
        )

    @action(detail=False, methods=["get"], url_path="group/(?P<group_id>[^/.]+)")
    def by_group(self, request, group_id=None):
        self.queryset = self.get_queryset().filter(group_id=group_id)
        return self.list(request)

    @action(detail=False, methods=["get"], url_path="teacher/(?P<teacher_id>[^/.]+)")
    def by_teacher(self, request, teacher_id):
        self.queryset = self.get_queryset().filter(teacher_id=teacher_id)
        return self.list(request)

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated],
    )
    def get_me(self, request):
        subscription = (
            Subscription.objects.filter(user=request.user)
            .select_related("content_type")
            .first()
        )
        if not subscription:
            raise NotFound(
                {
                    "code": "subscription_not_found",
                    "detail": "Подписка не найдена",
                    "source": {"pointer": "/subscription"},
                },
            )

        model_class = subscription.content_type.model_class()
        if model_class == Group:
            return self.by_group(request, subscription.object_id)
        elif model_class == Teacher:
            return self.by_teacher(request, subscription.object_id)
        else:
            raise ValidationError(
                {
                    "code": "invalid_subscription_type",
                    "detail": "Неверный тип подписки",
                    "source": {"pointer": "/subscription"},
                },
            )
