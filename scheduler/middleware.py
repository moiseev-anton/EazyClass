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
    # Only known non-credential parameters on resource endpoints. Authentication
    # and unknown routes deliberately have no query values in their logs.
    COMMON_QUERY_FIELDS = frozenset({"page[number]", "page[size]", "sort", "include", "format"})
    RESOURCE_QUERY_FIELDS = {
        "lessons": {"filter[group]", "filter[teacher]", "filter[classroom]", "filter[date_from]",
                    "filter[date_to]", "filter[date]", "filter[lesson_number]", "filter[subgroup]"},
        "groups": {"filter[faculty]", "filter[grade]"},
        "teachers": {"filter[starts_with]"},
        "subscription": {"filter[group]", "filter[teacher]"},
        "classrooms": set(), "faculties": set(), "users": set(), "social-accounts": set(),
        "group-subscriptions": set(), "teacher-subscriptions": set(),
    }

    @classmethod
    def _query_for_log(cls, request):
        match = getattr(request, "resolver_match", None)
        view = getattr(match, "func", None)
        basename = getattr(view, "initkwargs", {}).get("basename")
        if basename not in cls.RESOURCE_QUERY_FIELDS:
            return {}
        allowed = cls.COMMON_QUERY_FIELDS | cls.RESOURCE_QUERY_FIELDS[basename]
        # Preserve repeated values, with bounds on both count and size.
        query = {}
        for name in sorted(allowed):
            if name in request.GET:
                values = request.GET.getlist(name)
                query[name] = [value[:100] for value in values[:3]]
                if len(values) > 3:
                    query[name].append("[truncated]")
                if len(values) == 1:
                    query[name] = query[name][0]
        return query

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
            "query": RequestLoggingMiddleware._query_for_log(request),
            "status_code": status_code,
            "duration_ms": round((perf_counter() - started) * 1000, 3),
        }
        if exc is not None:
            logger.error("Обработка HTTP-запроса прервана ошибкой", extra={**extra, **safe_error_context(exc)})
        else:
            logger.info("HTTP-запрос обработан", extra=extra)
