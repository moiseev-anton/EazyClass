from collections import defaultdict

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

    @action(detail=False, methods=['get'])
    def grouped(self, request):
        # Получаем отфильтрованный queryset
        queryset = self.filter_queryset(self.get_queryset())

        # Сериализация данных
        serializer = self.get_serializer(queryset, many=True)
        lessons = serializer.data

        # Группировка по дате
        grouped_lessons = defaultdict(list)
        for lesson in lessons:
            date = lesson["period"]["date"]
            grouped_lessons[date].append(lesson)

        # Преобразуем в список для ответа
        response_data = [
            {"date": date, "lessons": lessons} for date, lessons in grouped_lessons.items()
        ]

        return Response(response_data)
