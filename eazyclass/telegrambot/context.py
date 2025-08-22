from contextvars import ContextVar
from typing import TypedDict


class RequestContext(TypedDict, total=False):
    user_id: str
    hmac: bool


request_context: ContextVar[RequestContext] = ContextVar("request_context", default={})


def get_context_prefix() -> str:
    """Определяет префикс ключа на основе ContextVar."""

    ctx = request_context.get({})
    prefix = f"{ctx.get('user_id', 'anonymous')}:" if ctx.get("hmac", False) else "public:"
    # print("получаем префикс ", prefix)
    return prefix
