class ChatBlocked(Exception):
    pass

def should_retry(exc: BaseException) -> bool:
    return not isinstance(exc, ChatBlocked)