from collections import defaultdict

from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from scheduler.api.filters import LessonFilter
from rest_framework.viewsets import ReadOnlyModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.response import Response

from scheduler.api.v1.serializers import LessonSerializer
from scheduler.models import Lesson


class LessonViewSet(ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    serializer_class = LessonSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = LessonFilter

    def get_queryset(self):
        return Lesson.objects.filter(is_active=True).select_related(
            "group", "teacher", "subject", "classroom", "period"
        ).order_by("period__date", "period__lesson_number", "subgroup")

    @action(detail=False, methods=['get'], url_path='group/(?P<group_id>[^/.]+)')
    def by_group(self, request, group_id):
        queryset = self.get_queryset().filter(group=group_id)
        queryset = self.filter_queryset(queryset)  # Применяем фильтры по датам
        return self._grouped_response(queryset)

    @action(detail=False, methods=['get'], url_path='teacher/(?P<teacher_id>[^/.]+)')
    def by_teacher(self, request, teacher_id):
        queryset = self.get_queryset().filter(teacher=teacher_id)
        queryset = self.filter_queryset(queryset)  # Применяем фильтры по датам
        return self._grouped_response(queryset)

    def _grouped_response(self, queryset):
        """Вспомогательный метод для группировки уроков по дате."""
        lessons = self.get_serializer(queryset, many=True).data
        grouped_lessons = defaultdict(list)
        for lesson in lessons:
            date = lesson["period"]["date"]
            grouped_lessons[date].append(lesson)
        return Response([{"date": date, "lessons": lessons} for date, lessons in grouped_lessons.items()])
