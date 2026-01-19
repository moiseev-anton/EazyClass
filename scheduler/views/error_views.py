import logging

from django.http import HttpResponse
from django.views.defaults import (
    page_not_found as django_page_not_found,
    server_error as django_server_error,
    bad_request as django_bad_request,
    permission_denied as django_permission_denied,
)
from rest_framework.exceptions import (
    NotFound,
    PermissionDenied,
    ValidationError,
    APIException,
)
from rest_framework.request import Request as DRFRequest
from rest_framework_json_api.exceptions import exception_handler
from rest_framework_json_api.renderers import JSONRenderer

logger = logging.getLogger(__name__)


class MockView:
    """Фейковое представление для обработки ошибок без view."""

    resource_name = "errors"
    renderer_classes = [JSONRenderer]


MOCK_VIEW = MockView()


def wants_json(request):
    """Проверяет, требуется ли клиенту JSON-ответ."""
    accept = request.META.get("HTTP_ACCEPT", "")
    # Проверяем путь или Accept заголовок
    is_api_request = request.path.startswith("/api/")
    return (
        is_api_request
        or "application/vnd.api+json" in accept
        or "application/json" in accept
    )


def handle_django_error(request, drf_exception, default_view, exception=None):
    """Обрабатывает Django-ошибку, возвращая JSON:API или HTML."""
    if wants_json(request):
        context = {"request": DRFRequest(request), "view": MOCK_VIEW}
        drf_response = exception_handler(drf_exception, context)
        logger.info(drf_response.data)
        renderer = JSONRenderer()
        renderer_context = {
            "request": request,
            "response": drf_response,
            "view": MOCK_VIEW,
        }
        rendered_content = renderer.render(
            drf_response.data,
            accepted_media_type="application/vnd.api+json",
            renderer_context=renderer_context,
        )
        return HttpResponse(
            content=rendered_content,
            status=drf_response.status_code,
            content_type="application/vnd.api+json",
        )
    # Возвращаем HTML для не-JSON клиентов
    return default_view(request, exception) if exception else default_view(request)


def error_400(request, exception=None):
    """Обработчик для HTTP 400 Bad Request."""
    return handle_django_error(
        request=request,
        drf_exception=ValidationError(detail="Некорректный запрос"),
        default_view=django_bad_request,
        exception=exception,
    )


def error_403(request, exception=None):
    """Обработчик для HTTP 403 Forbidden."""
    return handle_django_error(
        request=request,
        drf_exception=PermissionDenied(detail="Доступ запрещён"),
        default_view=django_permission_denied,
        exception=exception,
    )


def error_404(request, exception=None):
    """Обработчик для HTTP 404 Not Found."""
    return handle_django_error(
        request=request,
        drf_exception=NotFound(detail="Ресурс не найден"),
        default_view=django_page_not_found,
        exception=exception,
    )


def error_500(request):
    """Обработчик для HTTP 500 Server Error."""
    return handle_django_error(
        request=request,
        drf_exception=APIException(detail="Внутренняя ошибка сервера"),
        default_view=django_server_error,
    )
