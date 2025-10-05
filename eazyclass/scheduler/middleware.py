import logging

from rest_framework import status

logger = logging.getLogger(__name__)


class Clear304BodyMiddleware:
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
        headers = '\n'.join([f'{k}: {v}' for k, v in request.headers.items()])

        msg = ('\n=== Incoming Request ===\n'
               f"Method: {request.method}\n"
               f"Path: {request.get_full_path()}\n"
               "Headers:\n") + headers
        # Логируем метод, путь, заголовки и тело
        logger.info(msg)

        if request.body:
            try:
                logger.info("Body: %s", request.body.decode("utf-8"))
            except Exception:
                logger.warning("Could not decode request body")

        response = self.get_response(request)
        return response
