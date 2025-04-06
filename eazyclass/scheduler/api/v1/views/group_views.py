import logging

from django.db import models
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from scheduler.api.v1.serializers import (
    GroupSerializer,
)
from scheduler.api.v1.serializers.serializers import (
    BotFacultySerializer,
    BotFacultyMapSerializer,
)
from scheduler.authentication import HMACAuthentication
from scheduler.models import Group, Faculty

logger = logging.getLogger(__name__)


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class BotFacultyView(viewsets.ReadOnlyModelViewSet):
    authentication_classes = [HMACAuthentication]
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