from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema,
    inline_serializer,
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import serializers, status
from scheduler.api.mixins import PlainApiViewMixin
from scheduler.api.v1.serializers import TelegramTokenObtainSerializer
from scheduler.authentication import TelegramWebAppAuthentication
from .cookie_handler_mixin import TokenCookieHandlerMixin
from rest_framework.views import APIView

class TelegramTokenObtainView(
    TokenCookieHandlerMixin,
    PlainApiViewMixin,
    APIView
):
    authentication_classes = [TelegramWebAppAuthentication]
    permission_classes = [AllowAny]
    serializer_class = TelegramTokenObtainSerializer

    @extend_schema(
        tags=["Token"],
        summary="Obtain JWT tokens via Telegram WebApp initData",
        description=(
            "Authenticates a user using Telegram WebApp initData and returns a pair of JWT tokens.\n\n"
            "The client must send Telegram initData in the Authorization header:\n\n"
            "`Authorization: tma <initDataRaw>`\n\n"
            "The server validates Telegram signature, identifies (or creates) the user, "
            "and issues JWT tokens.\n\n"
            "**Browser clients (SPA, Telegram WebApp):**\n\n"
            "• Must include header `X-Client-Type: browser`\n\n"
            "• On success, refresh token is set in an HttpOnly cookie `refresh_token`\n\n"
            "• `refresh` field is removed from the response body\n\n"
            "**Non-browser clients:**\n\n"
            "• Refresh token is returned in the response body"
        ),
        auth=[],  # важно — без JWT
        parameters=[
            OpenApiParameter(
                name="Authorization",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=True,
                description=(
                    "Telegram WebApp initData.\n\n"
                    "Format: `tma <initDataRaw>`\n\n"
                    "`initDataRaw` is provided by Telegram Mini App via "
                    "`Telegram.WebApp.initData`."
                ),
            ),
            OpenApiParameter(
                name="X-Client-Type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.HEADER,
                required=False,
                description=(
                    "Set to `browser` for browser-based clients (Telegram WebApp, SPA).\n\n"
                    "This instructs the server to set refresh token in HttpOnly cookie "
                    "instead of returning it in the response body."
                ),
                enum=["browser"],
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=inline_serializer(
                    name="TelegramTokenResponse",
                    fields={
                        "access": serializers.CharField(help_text="Access token"),
                        "refresh": serializers.CharField(
                            required=False,
                            help_text="Refresh token (only for non-browser clients)",
                        ),
                    },
                ),
                description="Authentication successful",
                examples=[
                    OpenApiExample(
                        "Browser response",
                        value={"access": "eyJ..."},
                        media_type="application/json",
                    ),
                    OpenApiExample(
                        "Non-browser response",
                        value={
                            "access": "eyJ...",
                            "refresh": "eyJ...",
                        },
                        media_type="application/json",
                    ),
                ],
            ),
            401: OpenApiResponse(description="Invalid or expired Telegram initData"),
            400: OpenApiResponse(description="Authorization header missing or malformed"),
            503: OpenApiResponse(description="Authentication service unavailable"),
        },
    )
    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data={},
            context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        response = Response(data, status=status.HTTP_200_OK)

        if data.get("success") and self._is_browser_request(request):
            self._set_refresh_cookie(response, request)
            self._remove_refresh_from_body(response)

        return response
