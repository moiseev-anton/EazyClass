import logging
import uuid

from django.conf import settings
from django.core.cache import caches
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from scheduler.api.v1.serializers import GroupSerializer, BotAuthSerializer
from scheduler.models import Group

logger = logging.getLogger(__name__)

# Получаем кэш для аутентификации
auth_cache = caches['auth']

AUTH_TOKEN_TIMEOUT = 900  # 15 минут


class DeeplinkFactory:
    @classmethod
    def generate(cls, provider, nonce):
        templates = getattr(settings, 'AUTH_DEEPLINK_TEMPLATES', {})
        if provider not in templates:
            raise ValueError(f"Invalid provider: {provider}")

        return templates[provider].format(nonce=nonce)


class AuthViewSet(ViewSet):
    def list(self, request: Request):
        base_url = request.build_absolute_uri('/api/v1/auth/')
        return Response({
            "message": "Authentication endpoints",
            "available_actions": [
                {
                    "name": "generate-deeplink",
                    "method": "GET",
                    "url": f"{base_url}deeplink/<provider>/",
                    "description": "Generate a deeplink for bot authentication."
                },
                {
                    "name": "bot-auth",
                    "method": "POST",
                    "url": f"{base_url}bot/",
                    "description": "Authenticate a user via bot."
                },
            ]
        })

    # Генерация диплинка
    @action(detail=False, methods=['get'], url_path='deeplink/(?P<provider>[^/.]+)')
    def generate_deeplink(self, request: Request, provider):
        try:
            nonce = str(uuid.uuid4())
            deeplink = DeeplinkFactory.generate(provider, nonce)
            logger.info(f"Generated deeplink for provider {provider} with nonce {nonce}")
            return Response({"deeplink": deeplink, "nonce": nonce})
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

    # Обработка запроса от бота
    @action(detail=False, methods=['post'], url_path='bot')
    def bot_auth(self, request):
        serializer = BotAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, created = serializer.save()

        nonce = serializer.validated_data.get("token")
        if nonce:
            auth_cache.set(nonce, str(user.id), timeout=AUTH_TOKEN_TIMEOUT)
            nonce_status = 'authenticated'
            logger.info(f"User {user.id} authenticated with token {nonce}")
        else:
            nonce_status = 'none'
            logger.info(f"User {user.id} started bot without token")

        return Response({
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "username": user.username
            },
            "created": created,
            "nonce_status": nonce_status
        })


class GenerateDeeplinkView(APIView):
    def get(self, request: Request, provider):
        try:
            token = str(uuid.uuid4())
            deeplink = DeeplinkFactory.generate(provider, token)
            logger.info(f"Generated deeplink for provider {provider} with token {token}")
            return Response({"deeplink": deeplink, "token": token})
        except ValueError as e:
            return Response({"error": str(e)}, status=400)


class BotAuthView(APIView):
    def post(self, request: Request):
        serializer = BotAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, created = serializer.save()

        token = serializer.validated_data.get("token")
        if token:
            auth_cache.set(token, str(user.id), timeout=AUTH_TOKEN_TIMEOUT)
            token_status = 'authenticated'
            logger.info(f"User {user.id} authenticated with token {token}")
        else:
            token_status = 'none'
            logger.info(f"User {user.id} started bot without token")

        return Response({
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "username": user.username
            },
            "created": created,
            "token_status": token_status
        })


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
