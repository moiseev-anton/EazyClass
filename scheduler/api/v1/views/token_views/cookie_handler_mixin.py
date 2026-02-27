import logging

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.settings import api_settings

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
            secure=True,
            samesite="Lax",
            max_age=api_settings.REFRESH_TOKEN_LIFETIME.total_seconds(),
            path="/api/",
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
