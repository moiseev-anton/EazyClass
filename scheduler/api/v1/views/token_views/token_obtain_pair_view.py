import logging

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (extend_schema, inline_serializer, OpenApiExample, OpenApiParameter, OpenApiResponse)
from rest_framework import serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView

from scheduler.api.mixins import PlainApiViewMixin
from scheduler.api.v1.serializers import CustomTokenObtainPairSerializer
from .cookie_handler_mixin import TokenCookieHandlerMixin

logger = logging.getLogger(__name__)



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