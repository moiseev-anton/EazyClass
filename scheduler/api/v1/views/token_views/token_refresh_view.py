import logging

from django.utils.translation import gettext_lazy as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse)
from rest_framework import serializers, status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenRefreshView

from scheduler.api.mixins import PlainApiViewMixin
from scheduler.api.v1.serializers import CustomTokenRefreshSerializer
from .cookie_handler_mixin import TokenCookieHandlerMixin

logger = logging.getLogger(__name__)


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