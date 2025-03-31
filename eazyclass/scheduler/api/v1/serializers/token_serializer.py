from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.core.cache import caches
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import TokenError, AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from scheduler.authentication import CustomRefreshToken
import logging

logger = logging.getLogger(__name__)
cache = caches['auth']


class CustomTokenObtainPairSerializer(serializers.Serializer):
    nonce = serializers.UUIDField(write_only=True)
    token_class = CustomRefreshToken

    default_error_messages = {
        "invalid_nonce": _("Invalid or expired nonce"),
        "auth_in_progress": _("Waiting authentication via bot"),
        "no_active_account": _("No active account found for the given nonce"),
        "service_unavailable": _("Authentication service unavailable, try again later"),
    }

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        nonce = str(attrs.get("nonce"))

        try:
            user_id = cache.get(nonce)
        except Exception as e:
            logger.exception(str(e))
            raise APIException(self.error_messages["service_unavailable"])

        if not user_id:
            return {"success": False, "message": self.error_messages["auth_in_progress"]}

        user_model = get_user_model()
        user_id = user_id.encode('utf-8')

        try:
            user = user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except user_model.DoesNotExist:
            raise AuthenticationFailed(self.error_messages["no_active_account"], "no_active_account", )
        except Exception as e:
            logger.exception(str(e))
            raise APIException(self.error_messages["service_unavailable"])

        if not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        refresh = self.token_class.for_user(user)

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, user)

        try:
            cache.expire(nonce, 10)  # Уменьшаем TTL до 10 секунд
        except Exception as e:
            logger.exception(str(e))
            # Некритично если не получится сократить TTL (просто логируем)

        return {"success": True, "refresh": str(refresh), "access": str(refresh.access_token)}


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = CustomRefreshToken

    default_error_messages = {
        "invalid_token": _("Token is invalid or expired"),
        "no_active_account": _("No active account found for the given nonce"),
        "service_unavailable": _("Authentication service unavailable, try again later"),
    }

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        try:
            refresh = self.token_class(attrs["refresh"])  # verify и check_whitelist вызываются здесь
        except TokenError as e:
            raise AuthenticationFailed(
                self.error_messages.get("not_in_whitelist", str(e)),
                "invalid_token",
            )
        except Exception as e:
            logger.exception(str(e))
            raise APIException(self.error_messages["service_unavailable"])

        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
        if user_id and (
                user := get_user_model().objects.get(
                    **{api_settings.USER_ID_FIELD: user_id}
                )
        ):
            if not api_settings.USER_AUTHENTICATION_RULE(user):
                raise AuthenticationFailed(self.error_messages["no_active_account"], "no_active_account")

        data = {'access': str(refresh.access_token)}

        if api_settings.ROTATE_REFRESH_TOKENS:
            old_jti = refresh.payload[api_settings.JTI_CLAIM]

            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()

            refresh.add_to_whitelist()
            refresh.remove_from_whitelist(old_jti)
            data['refresh'] = str(refresh)

        return data
