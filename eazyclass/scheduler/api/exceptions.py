from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    # Получаем стандартный ответ от DRF
    response = exception_handler(exc, context)

    if response is not None:
        # Возвращаем только данные об ошибке
        return Response(
            {
                "code": response.status_code,
                "detail": response.data.get("detail", "Unknown error"),
            },
            status=response.status_code,
        )

    # Для необработанных исключений
    return Response({"code": 500, "message": str(exc)}, status=500)
