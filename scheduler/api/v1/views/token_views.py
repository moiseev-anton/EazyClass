import logging

from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse
from rest_framework import serializers, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from scheduler.api.mixins import PlainApiViewMixin
from scheduler.api.v1.serializers import (
    CustomTokenObtainPairSerializer,
    CustomTokenRefreshSerializer,
)
from scheduler.authentication import CustomRefreshToken

logger = logging.getLogger(__name__)


class TokenCookieHandlerMixin:
    """Миксин для обработки токенов в куках"""

    @staticmethod
    def _set_refresh_cookie(response: Response, request: Request) -> None:
        refresh_token = response.data.get("refresh")
        response.set_cookie(
            key="refresh_token",
            value=refresh_token,
            httponly=True,
            secure=request.is_secure(),
            samesite="None",
            max_age=api_settings.REFRESH_TOKEN_LIFETIME.total_seconds(),
        )

    @staticmethod
    def _remove_refresh_from_body(response: Response) -> None:
        if "refresh" in response.data:
            del response.data["refresh"]

    @staticmethod
    def _is_browser_request(request: Request) -> bool:
        client_type = request.headers.get("X-Client-Type", "").lower()
        accept_header = request.headers.get("Accept", "").lower()
        return client_type == "browser" or "text/html" in accept_header


class CustomTokenObtainPairView(
    TokenCookieHandlerMixin, PlainApiViewMixin, TokenObtainPairView
):
    serializer_class = CustomTokenObtainPairSerializer

    @extend_schema(
        tags=["Token"],
        summary="Obtain access and refresh tokens (non-JSON:API)",
        description=(
                "Returns a pair of JWT tokens (access and refresh).\n\n"
                "**Browser clients (SPA, web applications):**\n\n"
                "• Must include header `X-Client-Type: browser`\n\n"
                "• On success, refresh token is set in an HttpOnly cookie `refresh_token`\n\n"
                "• `refresh` field is removed from the response body\n\n"
                "**Non-browser clients (mobile apps, Postman, etc.):**\n\n"
                "• `X-Client-Type` header is not required\n\n"
                "• Refresh token is returned in the response body (`refresh` field)"
        ),
        auth=[],
        parameters=[
            OpenApiParameter(
                name="X-Client-Type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=False,
                description=(
                        "Set to `browser` for browser-based clients (SPA).\n\n"
                        "This instructs the server to set refresh token in HttpOnly cookie "
                        "instead of returning it in the response body."
                ),
                enum=["browser"],
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="TokenObtainResponse",
                    fields={
                        "success": serializers.BooleanField(
                            help_text="Authentication status"
                        ),
                        "access": serializers.CharField(help_text="Access token"),
                        "refresh": serializers.CharField(
                            required=False,
                            help_text="Refresh token (only for browser clients)",
                        ),
                    },
                ),
                description="Success",
                examples=[
                    OpenApiExample(
                        "Browser response",
                        value={"success": True, "access": "eyJ..."},
                        media_type="application/json",
                    ),
                    OpenApiExample(
                        "Non-browser response",
                        value={
                            "success": True,
                            "access": "eyJ...",
                            "refresh": "eyJ...",
                        },
                        media_type="application/json",
                    ),
                ],
            ),
            202: OpenApiResponse(
                response=inline_serializer(
                    name="AuthPendingResponse",
                    fields={
                        "success": serializers.BooleanField(),
                        "message": serializers.CharField(),
                    },
                ),
                description="Authentication in progress",
            ),
            400: OpenApiResponse(description="Invalid request"),
            401: OpenApiResponse(description="Authentication failed"),
            503: OpenApiResponse(description="Service unavailable"),
        },
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        status_code = (
            status.HTTP_200_OK if data.get("success") else status.HTTP_202_ACCEPTED
        )
        response = Response(data, status=status_code)

        if data.get("success") and self._is_browser_request(request):
            self._set_refresh_cookie(response, request)
            self._remove_refresh_from_body(response)

        return response


class CustomTokenRefreshView(
    TokenCookieHandlerMixin, PlainApiViewMixin, TokenRefreshView
):
    serializer_class = CustomTokenRefreshSerializer

    @extend_schema(
        tags=["Token"],
        summary="Refresh access and refresh tokens (non-JSON:API)",
        description=(
                "Accepts a refresh token (from request body or cookie) and returns a new access token "
                "(and optionally a new refresh token if rotation is enabled).\n\n"
                "**Browser clients (SPA, web applications):**\n\n"
                "• Must include header `X-Client-Type: browser`\n\n"
                "• Refresh token is read from HttpOnly cookie `refresh_token`\n\n"
                "• New refresh token (if rotated) is set in the cookie\n\n"
                "• `refresh` field is removed from the response body\n\n"
                "**Non-browser clients:**\n\n"
                "• `X-Client-Type` header is not required\n\n"
                "• Refresh token must be sent in the request body (`refresh` field)"
        ),
        request=inline_serializer(
            name="TokenRefreshRequest",
            fields={
                "refresh": serializers.CharField(
                    required=False,
                    help_text="Refresh token (required for non-browser clients; browser clients use cookie)",
                )
            },
        ),
        parameters=[
            OpenApiParameter(
                name="X-Client-Type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=False,
                description=(
                        "Set to `browser` for browser-based clients.\n"
                        "This tells the server to read refresh token from HttpOnly cookie "
                        "and set new one (if rotated) in cookie instead of response body."
                ),
                enum=["browser"],
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="TokenRefreshResponse",
                    fields={
                        "access": serializers.CharField(),
                        "refresh": serializers.CharField(required=False),
                    },
                ),
                description="Success",
                examples=[
                    OpenApiExample(
                        "Browser response",
                        value={"access": "eyJ..."},
                        media_type="application/json",
                    ),
                    OpenApiExample(
                        "Non-browser response",
                        value={"access": "eyJ...", "refresh": "eyJ..."},
                        media_type="application/json",
                    ),
                ],
            ),
            401: OpenApiResponse(description="Invalid token"),
        },
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        refresh_token = self._get_refresh_token(request)
        serializer = self.get_serializer(data={"refresh": refresh_token})
        serializer.is_valid(raise_exception=True)

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)

        if self._is_browser_request(request):
            self._set_refresh_cookie(response, request)
            self._remove_refresh_from_body(response)

        return response

    @staticmethod
    def _get_refresh_token(request: Request) -> str:
        """Извлекает refresh token из запроса"""
        if "refresh" in request.data:
            return request.data["refresh"]
        if "refresh_token" in request.COOKIES:
            return request.COOKIES["refresh_token"]
        raise AuthenticationFailed(_("Refresh token is missing"), "authorization")


class LogoutView(TokenCookieHandlerMixin, PlainApiViewMixin, APIView):
    """
    Выход пользователя:
    • удаляет refresh-токен из белого списка
    • удаляет httponly куку refresh_token
    """
    permission_classes = [IsAuthenticated]
    serializer_class = None

    @extend_schema(
        tags=["Token"],
        summary="Logout — invalidate refresh token and clear cookie (non-JSON:API)",
        description=(
                "Invalidates the current refresh token by removing it from the whitelist "
                "and clears the `refresh_token` HttpOnly cookie (if present).\n\n"
                "• Browser clients: refresh token is taken from cookie\n"
                "• Non-browser clients: refresh token should be sent in the request body (`refresh` field)\n\n"
                "The `X-Client-Type` header is **not required** and has no effect on the logout process "
                "(unlike token obtain/refresh endpoints)."
        ),
        methods=["POST"],
        request=inline_serializer(
            name="LogoutRequest",
            fields={
                "refresh": serializers.CharField(
                    required=False,
                    help_text="Refresh token (required for non-browser clients; browser clients use cookie)",
                )
            },
        ),
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="LogoutResponse",
                    fields={
                        "success": serializers.BooleanField(),
                        "detail": serializers.CharField(),
                    },
                ),
                description="Logout successful",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "success": True,
                            "detail": "Logout successful",
                        },
                    ),
                ],
            ),
            401: OpenApiResponse(
                description="Authentication credentials were not provided or are invalid",
            ),
            500: OpenApiResponse(
                description="Internal server error during logout process",
            ),
        },
    )
    def post(self, request, *args, **kwargs):
        # Пытаемся получить refresh-токен (из кук или из тела запроса)
        refresh_str = self._get_refresh_token_from_request(request)

        if not refresh_str:
            # Если токена вообще нет — считаем, что уже разлогинен
            return self._success_response(detail="Already logged out")

        try:
            refresh = CustomRefreshToken(refresh_str)

            # Удаляем из белого списка
            try:
                refresh.remove_from_whitelist()
            except Exception as e:
                logger.warning(f"Ошибка при удалении из whitelist: {e}", exc_info=True)
                # не падаем — куку всё равно надо удалить

            # Удаляем куку (если она была)
            response = self._success_response(detail="Logout successful")
            self._clear_refresh_cookie(response, request)
            return response

        except TokenError:
            # Токен битый / истёк / невалидный → просто чистим куку
            response = self._success_response(detail="Logout successful (invalid token)")
            self._clear_refresh_cookie(response, request)
            return response

        except Exception as e:
            logger.exception("Неожиданная ошибка при logout")
            return Response(
                {"detail": "Internal server error during logout"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def _get_refresh_token_from_request(request) -> str | None:
        # Сначала кука (основной сценарий для браузера)
        if "refresh_token" in request.COOKIES:
            return request.COOKIES["refresh_token"]

        # На всякий случай — тело запроса
        return request.data.get("refresh")

    @staticmethod
    def _clear_refresh_cookie(response: Response, request) -> None:
        response.set_cookie(
            key="refresh_token",
            value="",
            httponly=True,
            secure=request.is_secure(),
            samesite="None", # TODO: временно. заменить на "Strict"
            max_age=0,
            path="/",
        )

    @staticmethod
    def _success_response(detail: str = "Logout successful") -> Response:
        return Response(
            {
                "success": True,
                "detail": detail,
            },
            status=status.HTTP_200_OK
        )
