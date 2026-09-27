import logging

from rest_framework import status

logger = logging.getLogger(__name__)


class Clear304BodyMiddleware:
    """Для ответов с кодом 304 удаляет тело ответа"""
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code == status.HTTP_304_NOT_MODIFIED:
            response.content = b''  # Очистить тело
        return response


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        # Use the declared route, never user-provided URL values or credentials.
        match = getattr(request, "resolver_match", None)
        route = getattr(match, "route", None) or "<unresolved>"
        logger.info(
            "http.request.completed method=%s route=%s status_code=%s",
            request.method, route, response.status_code,
        )
        return response
