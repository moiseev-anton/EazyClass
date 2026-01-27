from django.utils.translation import gettext_lazy as _
from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
    OpenApiResponse,
    OpenApiExample,
)
from rest_framework import status, serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from scheduler.api.mixins import PlainApiViewMixin
from scheduler.api.v1.serializers import (
    CustomTokenObtainPairSerializer,
    CustomTokenRefreshSerializer,
)


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
            "Returns a pair of JWT tokens (access and refresh). "
            "If the client is a browser, the refresh token is set in an HttpOnly cookie."
        ),
        auth=[],
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
            "Accepts a refresh token from either the request body or cookie, "
            "and returns a new pair of JWT tokens. "
        ),
        auth=[],
        request=inline_serializer(
            name="TokenRefreshRequest",
            fields={
                "refresh": serializers.CharField(
                    required=False,
                    help_text="Refresh token (not needed for browser clients)",
                )
            },
        ),
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
