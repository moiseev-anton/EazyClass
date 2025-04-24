from drf_spectacular.openapi import AutoSchema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework.exceptions import AuthenticationFailed
from django.utils.translation import gettext_lazy as _

from scheduler.api.v1.serializers import CustomTokenObtainPairSerializer, CustomTokenRefreshSerializer


def set_refresh_token_cookie(response: Response) -> None:
    """
    Переносит refresh-токен из тела ответа в httponly cookie (актуально для браузеров)
    """
    if "refresh" in response.data:
        response.set_cookie(
            key="refresh_token",
            value=response.data["refresh"],
            httponly=True,
            secure=True,
            samesite="Lax",
            max_age=api_settings.REFRESH_TOKEN_LIFETIME.total_seconds(),
        )
        del response.data["refresh"]  # Убираем refresh из тела для браузеров


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
    schema = AutoSchema()

    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        is_browser = request.headers.get("X-Client-Type", "").lower() == "browser" or \
            "text/html" in request.headers.get("Accept", "").lower()

        status_code = status.HTTP_200_OK if data.get("success") else status.HTTP_202_ACCEPTED
        response = Response(data, status=status_code)

        if data.get("success") and is_browser:
            set_refresh_token_cookie(response)

        return response


class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer
    schema = AutoSchema()

    def post(self, request: Request, *args, **kwargs) -> Response:
        # Проверяем источник refresh-токена
        refresh_token_from_body = request.data.get("refresh")
        refresh_token_from_cookie = request.COOKIES.get("refresh_token")

        # Определяем источник и тип клиента
        if refresh_token_from_body:
            refresh_token = refresh_token_from_body
            is_browser = False
        elif refresh_token_from_cookie:
            refresh_token = refresh_token_from_cookie
            is_browser = True  # Браузер
        else:
            raise AuthenticationFailed(_("Refresh token is missing"), "authorization")
            # return Response({"error": "No refresh token provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Вызываем родительский метод для обработки запроса
        serializer = self.get_serializer(data={"refresh": refresh_token})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        response = Response(data, status=status.HTTP_200_OK)

        if is_browser:
            set_refresh_token_cookie(response)

        return response
