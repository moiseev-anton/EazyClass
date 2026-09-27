import logging
from time import perf_counter
from uuid import uuid4

from rest_framework import status

from eazyclass.logging_config import safe_error_context
from eazyclass.logging_context import logging_context

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
        # Do not trust/echo client-provided identifiers (or other header values).
        request.request_id = str(uuid4())
        started = perf_counter()
        with logging_context({"request_id": request.request_id}):
            try:
                response = self.get_response(request)
            except Exception as exc:
                self._log_result(request, started, 500, exc)
                raise
            response["X-Request-ID"] = request.request_id
            self._log_result(request, started, response.status_code)
            return response

    @staticmethod
    def _log_result(request, started, status_code, exc=None):
        # Use the declared route, never user-provided URL values or credentials.
        match = getattr(request, "resolver_match", None)
        extra = {
            "event": "http.request.completed", "method": request.method,
            "route": getattr(match, "route", None) or "<unresolved>",
            "status_code": status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
        }
        if exc is not None:
            logger.error("Обработка HTTP-запроса прервана ошибкой", extra={**extra, **safe_error_context(exc)})
        else:
            logger.info("HTTP-запрос обработан", extra=extra)
