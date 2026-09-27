"""Operation-local correlation, explicitly transported across process boundaries."""
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from uuid import UUID, uuid4


_context = ContextVar("logging_context", default=None)
REQUEST_HEADER = "eazyclass_request_id"
RUN_HEADER = "eazyclass_run_id"


def get_context():
    return dict(_context.get() or {})


def set_context(context):
    # Replace rather than merge: unrelated operations must not inherit fields.
    return _context.set(dict(context))


def reset_context(token):
    _context.reset(token)


@contextmanager
def logging_context(context):
    token = set_context(context)
    try:
        yield
    finally:
        reset_context(token)


class ContextFilter(logging.Filter):
    def filter(self, record):
        for key, value in get_context().items():
            record.__dict__.setdefault(key, value)
        return True


def _uuid(value):
    if not isinstance(value, str) or len(value) > 36:
        return None
    try:
        return str(UUID(value))
    except ValueError:
        return None


def publish_context(headers=None, **kwargs):
    """Celery protocol v2: copy correlation only, never args or credentials."""
    if headers is None:
        return
    context = get_context()
    headers[RUN_HEADER] = (
        _uuid(headers.get(RUN_HEADER)) or _uuid(context.get("run_id"))
        or _uuid(headers.get("root_id")) or _uuid(headers.get("id")) or str(uuid4())
    )
    request_id = _uuid(headers.get(REQUEST_HEADER)) or _uuid(context.get("request_id"))
    if request_id:
        headers[REQUEST_HEADER] = request_id
    else:
        headers.pop(REQUEST_HEADER, None)


def task_context_started(task=None, task_id=None, **kwargs):
    request = task.request
    headers = request.headers or {}
    context = {
        "task_id": task_id,
        "task_name": task.name,
        "attempt": request.retries + 1,
        "run_id": _uuid(headers.get(RUN_HEADER)) or _uuid(request.root_id)
                  or _uuid(task_id) or str(uuid4()),
    }
    request_id = _uuid(headers.get(REQUEST_HEADER))
    if request_id:
        context["request_id"] = request_id
    # Celery creates a request per execution; this also supports nested eager tasks.
    request._logging_context_token = set_context(context)


def task_context_finished(task=None, **kwargs):
    token = getattr(task.request, "_logging_context_token", None)
    if token is not None:
        reset_context(token)
        del task.request._logging_context_token


def clear_worker_context(**kwargs):
    # A fork must not inherit a previous operation's context.
    _context.set(None)
