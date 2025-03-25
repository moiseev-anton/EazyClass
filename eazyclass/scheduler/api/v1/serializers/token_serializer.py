from typing import Any

from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings

from scheduler.authentication import CustomRefreshToken


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    token_class = CustomRefreshToken


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    token_class = CustomRefreshToken

    def validate(self, attrs: dict[str, Any]) -> dict[str, str]:
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.payload.get(api_settings.USER_ID_CLAIM, None)
        if user_id and (
                user := get_user_model().objects.get(
                    **{api_settings.USER_ID_FIELD: user_id}
                )
        ):
            if not api_settings.USER_AUTHENTICATION_RULE(user):
                raise AuthenticationFailed(
                    self.error_messages["no_active_account"],
                    "no_active_account",
                )

        data = {'access': str(refresh.access_token)}

        if api_settings.ROTATE_REFRESH_TOKENS:
            refresh.remove_from_whitelist()
            refresh.set_jti()
            refresh.set_exp()
            refresh.set_iat()
            refresh.add_to_whitelist()

            data['refresh'] = str(refresh)

        return data
