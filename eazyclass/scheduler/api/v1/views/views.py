import logging
import uuid

from django.conf import settings
from django.core.cache import caches
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework_simplejwt.tokens import RefreshToken

from scheduler.api.v1.serializers import GroupSerializer, BotAuthSerializer, NonceSerializer
from scheduler.models import Group, User

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
    def list(self, request):
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
                {
                    "name": "check-auth-status",
                    "method": "GET",
                    "url": f"{base_url}status/?nonce=<nonce>",
                    "description": "Check the status of an authentication token."
                }
            ]
        })

    # Генерация диплинка
    @action(detail=False, methods=['get'], url_path='deeplink/(?P<provider>[^/.]+)')
    def generate_deeplink(self, request, provider):
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

    # Проверка статуса
    @action(detail=False, methods=['get'], url_path='status')
    def check_auth_status(self, request):
        serializer = NonceSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        nonce = serializer.validated_data['nonce']
        nonce_value = auth_cache.get(nonce)
        if not nonce_value:
            return Response({"status": False, "message": "Authentication not yet completed"}, status=202)
        try:
            user_id = int(nonce_value)
            user = User.objects.get(id=user_id)
            refresh = RefreshToken.for_user(user)
            logger.info(f"User {user.id} authenticated successfully with token {nonce}")
            return Response({
                "status": True,
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh)
            })
        except (ValueError, User.DoesNotExist):
            logger.error(f"Invalid user_id {nonce_value} or user not found for token {nonce}")
            return Response({"error": "Invalid user_id or user not found"}, status=401)


class GenerateDeeplinkView(APIView):
    def get(self, request, provider):
        try:
            token = str(uuid.uuid4())
            deeplink = DeeplinkFactory.generate(provider, token)
            logger.info(f"Generated deeplink for provider {provider} with token {token}")
            return Response({"deeplink": deeplink, "token": token})
        except ValueError as e:
            return Response({"error": str(e)}, status=400)


class BotAuthView(APIView):
    def post(self, request):
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


class CheckAuthStatusView(APIView):
    def get(self, request):
        serializer = TokenSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        token = serializer.validated_data['token']

        token_value = auth_cache.get(token)
        if not token_value:
            return Response({"status": False, "message": "Authentication not yet completed"}, status=202)

        try:
            user_id = int(token_value)
            user = User.objects.get(id=user_id)
            refresh = RefreshToken.for_user(user)
            # auth_cache.delete(token) # возможно стоит оставить до timeout
            return Response({
                "status": True,
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh)
            })
        except (ValueError, User.DoesNotExist):
            return Response({"error": "Invalid user_id or user not found"}, status=404)


class GroupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer
