import logging

from drf_spectacular.openapi import AutoSchema
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from scheduler.api.v1.serializers.serializers import (
    BotTeacherSerializer,
    BotTeacherMapSerializer,
)
from scheduler.authentication import HMACAuthentication
from scheduler.models import Teacher

logger = logging.getLogger(__name__)


class BotTeacherView(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]

    serializer_class = BotTeacherSerializer
    pagination_class = None
    http_method_names = ["get"]
    schema = AutoSchema()

    def get_queryset(self):
        return Teacher.objects.filter(is_active=True)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = BotTeacherMapSerializer(queryset)
        return Response(serializer.data)
