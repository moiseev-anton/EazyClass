from collections import defaultdict

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from scheduler.api.filters import LessonFilter
from scheduler.api.v1.serializers import LessonSerializer
from scheduler.models import Lesson, Subscription


class LessonViewSet(RetrieveModelMixin, GenericViewSet):
    permission_classes = [AllowAny]
    serializer_class = LessonSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = LessonFilter

    def get_queryset(self):
        return (
            Lesson.objects.filter(is_active=True)
            .select_related("group", "teacher", "subject", "classroom", "period")
            .order_by("period__date", "period__lesson_number", "subgroup")
        )

    # @method_decorator(cache_page(60 * 15))
    @action(detail=False, methods=["get"], url_path="group/(?P<group_id>[^/.]+)")
    def by_group(self, request, group_id):
        queryset = self.get_queryset().filter(group=group_id)
        queryset = self.filter_queryset(queryset)  # Применяем фильтры по датам
        return self._grouped_response(queryset)

    # @method_decorator(cache_page(60 * 15))
    @action(detail=False, methods=["get"], url_path="teacher/(?P<teacher_id>[^/.]+)")
    def by_teacher(self, request, teacher_id):
        queryset = self.get_queryset().filter(teacher=teacher_id)
        queryset = self.filter_queryset(queryset)  # Применяем фильтры по датам
        return self._grouped_response(queryset)

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated],
    )
    def get_me(self, request):
        """
        Возвращает уроки для объекта, на который подписан текущий пользователь.
        Применяет фильтры по дате из LessonFilter.
        """
        subscription = (
            Subscription.objects.filter(user=request.user)
            .select_related("content_type")
            .first()
        )
        if not subscription:
            return Response(
                {"detail": "Подписка не найдена"}, status=status.HTTP_404_NOT_FOUND
            )

        content_type = subscription.content_type.model
        object_id = subscription.object_id

        queryset = self.get_queryset()
        if content_type == "group":
            return self.by_group(request, object_id)
        elif content_type == "teacher":
            return self.by_teacher(request, object_id)
        else:
            return Response(
                {"detail": "Неверный тип подписки"}, status=status.HTTP_400_BAD_REQUEST
            )

    def _grouped_response(self, queryset):
        """Вспомогательный метод для группировки уроков по дате."""
        lessons = self.get_serializer(queryset, many=True).data
        grouped_lessons = defaultdict(list)
        for lesson in lessons:
            date = lesson["period"]["date"]
            grouped_lessons[date].append(lesson)
        return Response(
            [
                {"date": date, "lessons": lessons}
                for date, lessons in grouped_lessons.items()
            ]
        )
