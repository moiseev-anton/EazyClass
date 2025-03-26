from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from scheduler.api.v1.serializers import CustomTokenObtainPairSerializer, CustomTokenRefreshSerializer


def is_browser(request: Request) -> bool:
    """Проверяет тип клиента. True если браузер."""
    return request.headers.get("X-Client-Type", "").lower() == "browser" or \
        "text/html" in request.headers.get("Accept", "").lower()


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        status_code = status.HTTP_200_OK if data.get("success") else status.HTTP_202_ACCEPTED
        response = Response(data, status=status_code)

        if data.get("success"):
            if is_browser(request):
                response.set_cookie(
                    key="refresh_token",
                    value=data["refresh"],
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                    max_age=api_settings.REFRESH_TOKEN_LIFETIME.total_seconds(),
                )
                del data["refresh"]

        return response


class CustomTokenRefreshView(TokenRefreshView):
    serializer_class = CustomTokenRefreshSerializer

    def post(self, request: Request, *args, **kwargs) -> Response:
        # Проверяем наличие refresh-токена в теле или куке
        refresh_token = request.data.get("refresh") or request.COOKIES.get("refresh_token")
        if not refresh_token:
            return Response({"error": "No refresh token provided"}, status=status.HTTP_400_BAD_REQUEST)

        # Вызываем родительский метод для обработки запроса
        serializer = self.get_serializer(data={"refresh": refresh_token})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        response = Response(data, status=status.HTTP_200_OK)

        if "refresh" in data:
            if is_browser(request):
                response.set_cookie(
                    key="refresh_token",
                    value=data["refresh"],
                    httponly=True,
                    secure=True,
                    samesite="Lax",
                    max_age=api_settings.REFRESH_TOKEN_LIFETIME.total_seconds(),
                )
                del data["refresh"]

        return response
