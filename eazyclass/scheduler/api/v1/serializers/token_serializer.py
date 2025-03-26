from typing import Any

from django.contrib.auth import get_user_model
from django.contrib.auth.models import update_last_login
from django.core.cache import caches
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import APIException
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from scheduler.authentication import CustomRefreshToken

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
        except Exception:
            raise APIException(self.error_messages["service_unavailable"])

        if not user_id:
            return {"success": False, "message": self.error_messages["auth_in_progress"]}

        user_model = get_user_model()
        try:
            # Находим пользователя по user_id
            user = user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id.decode('utf-8')})
        except user_model.DoesNotExist:
            raise AuthenticationFailed(self.error_messages["no_active_account"], "no_active_account", )
        except Exception:
            raise APIException(self.error_messages["service_unavailable"])

        if not api_settings.USER_AUTHENTICATION_RULE(user):
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        refresh = self.token_class.for_user(user)

        if api_settings.UPDATE_LAST_LOGIN:
            update_last_login(None, user)

        return {"success": True, "refresh": str(refresh), "access": str(refresh.access_token)}


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = CustomRefreshToken

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        request = self.context["request"]

        refresh_token = attrs.get("refresh")
        if not refresh_token:
            refresh_token = request.COOKIES.get(api_settings.AUTH_COOKIE)

        if not refresh_token:
            raise AuthenticationFailed("Refresh token is missing", "authorization")

        refresh = self.token_class(refresh_token)
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
            refresh.remove_from_whitelist()
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            refresh.add_to_whitelist()

            data['refresh'] = str(refresh)

        return data
