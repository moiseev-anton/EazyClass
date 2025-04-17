import logging

from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from scheduler.api.filters import LessonFilter
from scheduler.api.v1.serializers import LessonSerializer, CompactLessonSerializer
from scheduler.models import Lesson, Subscription

logger = logging.getLogger(__name__)


class LessonViewSet(ModelViewSet):
    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
    filterset_class = LessonFilter

    permission_classes_by_action = {
        "group": [AllowAny],
        "teacher": [AllowAny],
        "me": [IsAuthenticated],
        "default": [IsAuthenticated],
    }

    def get_permissions(self):
        try:
            return [
                permission()
                for permission in self.permission_classes_by_action[self.action]
            ]
        except KeyError:
            return [
                permission()
                for permission in self.permission_classes_by_action["default"]
            ]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("group", "teacher", "subject", "classroom", "period")
            .order_by("period__date", "period__lesson_number", "subgroup")
        )

    def get_serializer_class(self):
        # Получаем формат из допустимого JSON:API фильтра
        response_format = self.request.query_params.get("filter[format]", "full")
        logger.info(f"Формат: {response_format}")

        if response_format == "compact":
            return CompactLessonSerializer
        return LessonSerializer

    # @method_decorator(cache_page(60 * 15))
    @action(detail=False, methods=["get"], url_path="group/(?P<group_id>[^/.]+)")
    def by_group(self, request, group_id=None):
        queryset = self.get_queryset().filter(group_id=group_id)
        queryset = self.filter_queryset(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    # @method_decorator(cache_page(60 * 15))
    @action(detail=False, methods=["get"], url_path="teacher/(?P<teacher_id>[^/.]+)")
    def by_teacher(self, request, teacher_id):
        queryset = self.get_queryset().filter(teacher_id=teacher_id)
        queryset = self.filter_queryset(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

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
                }
            )

        content_type = subscription.content_type.model
        object_id = subscription.object_id

        if content_type == "group":
            return self.by_group(request, object_id)
        elif content_type == "teacher":
            return self.by_teacher(request, object_id)
        else:
            raise ValidationError(
                {
                    "code": "invalid_subscription_type",
                    "detail": "Неверный тип подписки",
                    "source": {"pointer": "/subscription"},
                }
            )

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({"detail": "Method not allowed"}, status=403)
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({"detail": "Method not allowed"}, status=403)
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return Response({"detail": "Method not allowed"}, status=403)
        return super().destroy(request, *args, **kwargs)
