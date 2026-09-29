from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError
import logging

from rest_framework_json_api.exceptions import exception_handler as json_api_exception_handler
from rest_framework_simplejwt.exceptions import AuthenticationFailed as JWTAuthenticationFailed
from eazyclass.logging_config import safe_error_context

logger = logging.getLogger(__name__)
REASON_LABELS = {
    "invalid_request": "неверные данные запроса",
    "authentication_required_or_invalid": "отсутствуют или неверны данные аутентификации",
    "access_denied": "доступ запрещён", "not_found": "объект не найден",
    "method_not_allowed": "метод не разрешён", "conflict": "конфликт данных",
    "unsupported_media_type": "формат данных не поддерживается",
    "throttled": "превышена частота запросов", "server_error": "внутренний сбой",
    "request_rejected": "запрос не может быть выполнен",
    "no_active_account": "активный пользователь не найден",
    "invalid_token": "токен недействителен", "token_not_valid": "токен недействителен",
    "not_authenticated": "требуется аутентификация", "permission_denied": "недостаточно прав",
    "hmac_timestamp_out_of_range": "истекло допустимое время HMAC-запроса",
    "hmac_invalid_timestamp": "неверный формат времени HMAC-запроса",
    "hmac_signature_mismatch": "подпись HMAC не прошла проверку",
    "twa_invalid_header": "неверный формат заголовка Telegram WebApp",
    "twa_missing_hash": "отсутствует подпись Telegram WebApp",
    "twa_signature_mismatch": "подпись Telegram WebApp не прошла проверку",
    "twa_expired": "данные Telegram WebApp устарели",
}


def logging_exception_handler(exc, context):
    """Keep the configured JSON:API response contract; add safe diagnostics."""
    response = json_api_exception_handler(exc, context)
    # Unhandled exceptions continue to Django's existing exception logging.
    if response is None or getattr(exc, "_logging_reported", False):
        return response
    request = context.get("request")
    # Authentication may itself have failed: do not trigger request.user again.
    user = getattr(request, "_user", None)
    user_id = getattr(user, "pk", None)
    server_error = response.status_code >= 500
    reason = getattr(exc, "_log_reason", None) or {
        400: "invalid_request", 401: "authentication_required_or_invalid",
        403: "access_denied", 404: "not_found", 405: "method_not_allowed",
        409: "conflict", 415: "unsupported_media_type", 429: "throttled",
    }.get(response.status_code, "server_error" if server_error else "request_rejected")
    # Only fixed, known codes: never log validation details or arbitrary values.
    codes = exc.get_codes() if hasattr(exc, "get_codes") else None
    if isinstance(codes, str) and codes in {"no_active_account", "invalid_token", "not_authenticated", "permission_denied", "throttled"}:
        reason = codes
    elif isinstance(exc, JWTAuthenticationFailed) and isinstance(exc.detail, dict):
        code = exc.detail.get("code")
        if isinstance(code, str) and code in {"no_active_account", "invalid_token", "token_not_valid"}:
            reason = code
    message = "Ошибка при обработке API-запроса: %s" if server_error else "API-запрос отклонён: %s"
    logger.log(
        logging.ERROR if server_error else logging.INFO,
        message, REASON_LABELS.get(reason, "запрос не может быть выполнен"),
        extra={"event": "api.request.failed" if server_error else "api.request.rejected",
               "status_code": response.status_code, "reason": reason, "user_id": user_id,
               **(safe_error_context(exc) if server_error else {})},
    )
    return response


def flatten_validation_errors(errors, path=""):
    flat = []
    if isinstance(errors, list):
        for err in errors:
            flat.append({
                "detail": str(err),
                "source": {"pointer": path or "/"}
            })
    elif isinstance(errors, dict):
        for field, value in errors.items():
            new_path = f"{path}/{field}" if path else f"/{field}"
            flat.extend(flatten_validation_errors(value, new_path))
    else:
        flat.append({
            "detail": str(errors),
            "source": {"pointer": path or "/"}
        })
    return flat


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    errors = []

    if response is not None:
        status_code = response.status_code

        if isinstance(exc, DRFValidationError):
            raw_errors = flatten_validation_errors(response.data)
            for err in raw_errors:
                errors.append({
                    'code': str(getattr(exc, 'code', 'validation_error')),
                    'detail': err['detail'],
                    'source': err['source']
                })
        else:
            detail = response.data.get('detail', str(exc) or 'Unknown error')
            code = str(getattr(exc, 'default_code', 'error'))
            errors.append({
                'code': code,
                'detail': detail,
                'source': {'pointer': '/'}
            })

        return Response({"errors": errors}, status=status_code)

    # Необработанные исключения
    if isinstance(exc, DjangoValidationError):
        raw_errors = flatten_validation_errors(
            exc.message_dict if hasattr(exc, 'message_dict') else {'error': str(exc)}
        )
        for err in raw_errors:
            errors.append({
                'code': 'validation_error',
                'detail': err['detail'],
                'source': err['source']
            })
    else:
        errors.append({
            'code': 'server_error',
            'detail': str(exc) or 'An unexpected error occurred',
            'source': {'pointer': '/'}
        })

    return Response({"errors": errors}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
