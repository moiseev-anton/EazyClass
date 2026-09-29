from rest_framework.exceptions import AuthenticationFailed


def authentication_rejected(detail, reason):
    """Keep the public error unchanged; attach a fixed, internal logging reason."""
    exc = AuthenticationFailed(detail)
    exc._log_reason = reason
    return exc
