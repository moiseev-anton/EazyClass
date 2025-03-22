import logging
import uuid

from django.conf import settings
from django.core.cache import caches
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from scheduler.api.v1.serializers import GroupSerializer, BotAuthSerializer, TokenSerializer
from scheduler.models import Group, User

logger = logging.getLogger(__name__)

# Получаем кэш для аутентификации
auth_cache = caches['auth']


class DeeplinkFactory:
    @classmethod
    def generate(cls, provider, token):
        templates = getattr(settings, 'AUTH_DEEPLINK_TEMPLATES', {})
        if provider not in templates:
            raise ValueError(f"Invalid provider: {provider}")

        return templates[provider].format(token=token)


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
            auth_cache.set(token, str(user.id), timeout=300)
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
