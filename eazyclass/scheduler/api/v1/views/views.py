import logging
import uuid

from django.conf import settings
from django.core.cache import caches
from django.db import models
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from scheduler.api.v1.serializers import GroupSerializer, BotAuthSerializer, NonceSerializer
from scheduler.api.v1.serializers.serializers import BotFacultySerializer, BotFacultyMapSerializer
from scheduler.authentication import HMACAuthentication
from scheduler.models import Group, Faculty

logger = logging.getLogger(__name__)

# Получаем кэш для аутентификации
auth_cache = caches['auth']

NONCE_TIMEOUT = 300  # 5 минут


class DeeplinkFactory:
    @classmethod
    def generate(cls, provider, nonce):
        templates = getattr(settings, 'AUTH_DEEPLINK_TEMPLATES', {})
        if provider not in templates:
            raise ValueError(f"Invalid provider: {provider}")

        return templates[provider].format(nonce=nonce)


class DeeplinkView(APIView):
    def get(self, request: Request, provider):
        try:
            nonce = str(uuid.uuid4())
            deeplink = DeeplinkFactory.generate(provider, nonce)
            logger.info(f"Generated deeplink for provider {provider} with nonce {nonce}")
            return Response({"deeplink": deeplink, "nonce": nonce})
        except ValueError as e:
            return Response({"error": str(e)}, status=400)


class BotAuthView(APIView):
    authentication_classes = [HMACAuthentication]
    permission_classes = [AllowAny]

    def post(self, request: Request):
        user = request.user

        if user is None or not user.is_authenticated:
            serializer = BotAuthSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            user, created = serializer.save()
        else:
            created = False

        nonce_serializer = NonceSerializer(data=request.data)
        nonce_serializer.is_valid(raise_exception=True)
        nonce_status = nonce_serializer.save_nonce(user_id=str(user.id), timeout=300)

        return Response({
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "username": user.username
            },
            "created": created,
            "nonce_status": nonce_status
        }, status=status.HTTP_200_OK)


# =====================================================================

class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer


class BotFacultyView(viewsets.ReadOnlyModelViewSet):
    serializer_class = BotFacultySerializer
    pagination_class = None
    http_method_names = ['get']

    def get_queryset(self):
        return Faculty.objects.filter(is_active=True).prefetch_related(
            models.Prefetch(
                'groups',
                queryset=Group.objects.filter(is_active=True).order_by('grade', 'title'),
                to_attr='active_groups'
            )
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = BotFacultyMapSerializer(queryset)
        return Response(serializer.data)
