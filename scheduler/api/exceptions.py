from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as DRFValidationError


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
