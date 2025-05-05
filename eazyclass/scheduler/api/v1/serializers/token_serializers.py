from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.core.cache import caches
from django.utils.translation import gettext_lazy as _
from rest_framework_json_api import serializers
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import TokenError, AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from scheduler.authentication import CustomRefreshToken
import logging

logger = logging.getLogger(__name__)
cache = caches['auth']


class BaseTokenSerializer(serializers.Serializer):
    """Базовый сериализатор токенов"""

    default_error_messages = {
        "no_active_account": _("No active account found"),
        "service_unavailable": _("Authentication service unavailable, try again later"),
        "invalid_nonce": _("Invalid or expired nonce"),
        "auth_in_progress": _("Waiting authentication via bot"),
        "invalid_token": _("Token is invalid or expired"),
    }

    def _handle_service_exception(self, exc):
        """Логирование и обработка сервисных исключений"""
        logger.exception(str(exc))
        raise APIException(self.error_messages["service_unavailable"])

    def _validate_user(self, user_id: str):
        """Проверка существования и активности пользователя"""
        try:
            user = get_user_model().objects.get(
                **{api_settings.USER_ID_FIELD: user_id}
            )
            if not api_settings.USER_AUTHENTICATION_RULE(user):
                raise AuthenticationFailed(
                    self.error_messages["no_active_account"],
                    "no_active_account"
                )
            return user
        except get_user_model().DoesNotExist:
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account"
            )
        except Exception as e:
            self._handle_service_exception(e)


class CustomTokenObtainPairSerializer(BaseTokenSerializer):
    NONCE_TTL_REDUCTION = 10

    nonce = serializers.UUIDField(write_only=True)
    token_class = CustomRefreshToken

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        nonce = str(attrs.get("nonce"))

        try:
            user_id = cache.get(nonce)
            if not user_id:
                return {"success": False, "message": self.error_messages["auth_in_progress"]}

            user = self._validate_user(user_id)
            refresh = self.token_class.for_user(user)

            if api_settings.UPDATE_LAST_LOGIN:
                update_last_login(None, user)

            self._reduce_nonce_ttl(nonce)

            return {
                "success": True,
                "refresh": str(refresh),
                "access": str(refresh.access_token)
            }
        except Exception as e:
            self._handle_service_exception(e)

    def _reduce_nonce_ttl(self, nonce: str):
        """Уменьшает TTL nonce в Redis"""
        try:
            cache.expire(nonce, self.NONCE_TTL_REDUCTION)
        except Exception as e:
            logger.warning(f"Failed to reduce nonce TTL: {str(e)}")


class CustomTokenRefreshSerializer(BaseTokenSerializer, TokenRefreshSerializer):
    token_class = CustomRefreshToken

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        try:
            refresh = self.token_class(attrs["refresh"])
            user_id = refresh.payload.get(api_settings.USER_ID_CLAIM)

            if user_id:
                self._validate_user(user_id)

            data = {'access': str(refresh.access_token)}

            if api_settings.ROTATE_REFRESH_TOKENS:
                data.update(self._rotate_refresh_token(refresh))

            return data
        except TokenError as e:
            raise AuthenticationFailed(str(e), "invalid_token")
        except Exception as e:
            self._handle_service_exception(e)

    @staticmethod
    def _rotate_refresh_token(refresh):
        """Генерация нового refresh токена с ротацией"""
        old_jti = refresh.payload[api_settings.JTI_CLAIM]

        refresh.set_jti()
        refresh.set_exp()
        refresh.set_iat()

        refresh.add_to_whitelist()
        refresh.remove_from_whitelist(old_jti)

        return {'refresh': str(refresh)}


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Access token")
    refresh = serializers.CharField(
        required=False,
        help_text="Refresh token (only for browser clients)"
    )
    success = serializers.BooleanField(help_text="Authentication status")
