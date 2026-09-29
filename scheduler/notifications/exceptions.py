import requests
from telebot.apihelper import ApiHTTPException, ApiTelegramException


class ChatBlocked(Exception):
    pass

def should_retry(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.ConnectionError, requests.exceptions.Timeout)):
        return True
    if isinstance(exc, ApiTelegramException):
        return exc.error_code == 429 or 500 <= exc.error_code < 600
    if isinstance(exc, ApiHTTPException):
        return 500 <= exc.result.status_code < 600
    return False


def failure_reason(exc):
    if isinstance(exc, ChatBlocked):
        return "forbidden"
    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "connection_error"
    if isinstance(exc, ApiTelegramException):
        return "rate_limited" if exc.error_code == 429 else "api_error"
    if isinstance(exc, ApiHTTPException):
        return "http_error"
    return "unexpected_error"
