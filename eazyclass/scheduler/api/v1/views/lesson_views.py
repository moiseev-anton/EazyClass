import logging

from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiParameter,
    extend_schema_view,
)
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, NotFound
from rest_framework.permissions import IsAuthenticated, AllowAny

from scheduler.api.filters import LessonFilter
from scheduler.api.mixins import JsonApiMixin
from scheduler.api.v1.serializers import LessonSerializer
from scheduler.api.viewsets import ReadOnlyModelViewSet
from scheduler.models import Lesson, Subscription, Group, Teacher

logger = logging.getLogger(__name__)


@extend_schema_view(
    list=extend_schema(
        tags=["Lessons"],
        summary="Get Lessons",
        description="Returns a list of lessons.\n"
        "At least one of 'group' or 'teacher' filter is required`",
        parameters=[
            OpenApiParameter(name="filter[search]", exclude=True),
        ],
        auth=[],
        responses={
            200: LessonSerializer(many=True),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
    retrieve=extend_schema(
        tags=["Lessons"],
        summary="Get Lesson",
        description="Returns a specific lesson.",
        auth=[],
        responses={
            200: LessonSerializer(many=False),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
    get_me=extend_schema(
        tags=["Lessons"],
        summary="Get My Lessons",
        operation_id="lessons_me_list",
        description="Returns a list of lessons for the current user based on their subscription.",
        parameters=[
            OpenApiParameter(name="filter[search]", exclude=True),
            OpenApiParameter(name="filter[teacher]", exclude=True),
            OpenApiParameter(name="filter[group]", exclude=True),
        ],
        responses={
            200: LessonSerializer(many=True),
            400: OpenApiResponse(description="Bad Request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Not Found"),
        },
    ),
)
class LessonViewSet(JsonApiMixin, ReadOnlyModelViewSet):
    """
    Представление для получения информации об уроках.

    Поддерживает:
    - Список уроков (GET /lessons/) с фильтрацией по группе, преподавателю, датам и подгруппе.
    - Детали урока (GET /lessons/{id}/) без фильтров.
    - Персонализированный список уроков (GET /lessons/me/) для текущего пользователя на основе его подписки.
    """

    queryset = Lesson.objects.all()
    serializer_class = LessonSerializer
    filterset_class = LessonFilter
    permission_classes = [AllowAny]
    resource_name = "lessons"

    select_for_includes = {
        "__all__": [],
        "group": ["group"],
        "teacher": ["teacher"],
    }

    def get_queryset(self):
        """
        Возвращает отфильтрованный и оптимизированный набор уроков.
        Включает только активные уроки с предварительной загрузкой связанных данных.
        """
        return (
            super()
            .get_queryset()
            .filter(is_active=True)
            .select_related("subject", "classroom", "period")
            .order_by("period__date", "period__lesson_number", "subgroup")
        )

    def filter_queryset(self, queryset):
        """Отключает фильтры для действия 'retrieve', чтобы запрос по ID не требовал параметров."""
        if self.action == "retrieve":
            return queryset
        return super().filter_queryset(queryset)

    @action(
        detail=False,
        methods=["get"],
        url_path="me",
        permission_classes=[IsAuthenticated],
    )
    def get_me(self, request):
        """Возвращает список уроков для текущего пользователя на основе его подписки."""
        subscription = (
            Subscription.objects.filter(user=request.user)
            .select_related("content_type")
            .first()
        )
        if not subscription:
            raise NotFound(_("Subscription not found"), "subscription_not_found")

        model_class = subscription.content_type.model_class()
        if model_class == Group:
            self.queryset = self.get_queryset().filter(group_id=subscription.object_id)
        elif model_class == Teacher:
            self.queryset = self.get_queryset().filter(
                teacher_id=subscription.object_id
            )
        else:
            raise ValidationError(
                _("Invalid subscription type"), "invalid_subscription_type"
            )
        return self.list(request)
