import logging
import uuid

from django.conf import settings
from django.core.cache import caches
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from scheduler.api.v1.serializers import (
    BotAuthSerializer,
    NonceSerializer,
)
from scheduler.authentication import HMACAuthentication, IsHMACAuthenticated

logger = logging.getLogger(__name__)

# Получаем кэш для аутентификации
auth_cache = caches["auth"]

NONCE_TIMEOUT = 300  # 5 минут


class DeeplinkFactory:
    @classmethod
    def generate(cls, platform, nonce):
        templates = getattr(settings, "AUTH_DEEPLINK_TEMPLATES", {})
        if platform not in templates:
            raise ValueError(f"Invalid platform: {platform}")

        return templates[platform].format(nonce=nonce)


class DeeplinkView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Request, platform):
        try:
            nonce = str(uuid.uuid4())
            deeplink = DeeplinkFactory.generate(platform, nonce)
            logger.info(
                f"Generated deeplink for platform {platform} with nonce {nonce}"
            )
            return Response({"deeplink": deeplink, "nonce": nonce})
        except ValueError as e:
            return Response({"error": str(e)}, status=400)


class BotAuthView(APIView):
    authentication_classes = [HMACAuthentication]
    permission_classes = [IsHMACAuthenticated]

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

        return Response(
            {
                "user": {
                    "id": user.id,
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "username": user.username,
                },
                "created": created,
                "nonce_status": nonce_status,
            },
            status=status.HTTP_200_OK,
        )
