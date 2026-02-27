import logging

from drf_spectacular.utils import (extend_schema, inline_serializer, OpenApiExample, OpenApiResponse)
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError

from scheduler.api.mixins import PlainApiViewMixin
from scheduler.authentication import CustomRefreshToken
from .cookie_handler_mixin import TokenCookieHandlerMixin

logger = logging.getLogger(__name__)


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
            secure=True,
            samesite="Lax",
            max_age=0,
            path="/api/",
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
