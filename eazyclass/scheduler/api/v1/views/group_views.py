import logging

from django.db import models
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from scheduler.api.filters import GroupFilter
from scheduler.api.permissions import IsAdminOrReadOnly
from scheduler.api.v1.serializers import GroupSerializer, CompactGroupSerializer
from scheduler.api.v1.serializers.serializers import BotFacultySerializer, BotFacultyMapSerializer
from scheduler.models import Group, Faculty

logger = logging.getLogger(__name__)


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAdminOrReadOnly]
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
    filterset_class = GroupFilter
    pagination_class = None
    http_method_names = ["get"]

    def get_queryset(self):
        return Group.objects.filter(is_active=True).select_related('faculty').order_by('grade', 'title')

    def get_serializer_class(self):
        response_format = self.filterset.form.cleaned_data.get('format', 'full')
        logger.info(f"Формат: {response_format}")
        if response_format == 'compact':
            return CompactGroupSerializer
        return GroupSerializer

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)



class BotFacultyView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]

    serializer_class = BotFacultySerializer
    pagination_class = None
    http_method_names = ["get"]

    def get_queryset(self):
        return Faculty.objects.filter(is_active=True).prefetch_related(
            models.Prefetch(
                "groups",
                queryset=Group.objects.filter(is_active=True).order_by(
                    "grade", "title"
                ),
                to_attr="active_groups",
            )
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = BotFacultyMapSerializer(queryset)
        return Response(serializer.data)
