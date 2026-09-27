"""Shared logging formats. No Django settings access during module import."""
import copy
from datetime import datetime, timezone
import json
import logging
import logging.config
import math
from pathlib import Path


# Explicit output schema: never serialize arbitrary LogRecord extras or objects.
CONTEXT_FIELDS = frozenset({
    "event", "user_id", "user_created", "platform", "method", "route",
    "status_code", "duration_ms", "outcome", "reason", "attempt",
    "request_id", "task_id", "run_id", "task_name", "queue",
    "group_id", "period_id", "start_date", "end_date", "error_type",
    "error_stack", "count", "added_count", "updated_count", "removed_count",
    "success_count", "failed_count", "skipped_count", "retry_delay_seconds",
})
STACK_FIELDS = frozenset({"error_type", "frames", "file", "line", "function"})


def safe_error_context(exc):
    """Keep exception types and frame locations, never values/source/locals.

    Build plain data at the call site so sensitive exception objects aren't
    retained in LogRecords or handed to another handler accidentally.
    """
    chain, seen = [], set()
    current = exc
    while current is not None and id(current) not in seen and len(chain) < 8:
        seen.add(id(current))
        frames = []
        tb = current.__traceback__
        while tb is not None:
            frames.append({
                "file": Path(tb.tb_frame.f_code.co_filename).name,
                "line": tb.tb_lineno,
                "function": tb.tb_frame.f_code.co_name,
            })
            tb = tb.tb_next
        chain.append({"error_type": type(current).__name__, "frames": frames[-40:]})
        current = current.__cause__ or (
            None if current.__suppress_context__ else current.__context__
        )
    return {"error_type": type(exc).__name__, "error_stack": chain}


def _safe_value(value, depth=0):
    if value is None or type(value) in (str, int, bool):
        return value[:2000] if isinstance(value, str) else value
    if type(value) is float:
        return value if math.isfinite(value) else None
    if depth >= 6:
        return "[omitted]"
    if type(value) is dict:
        return {k: _safe_value(v, depth + 1) for k, v in value.items() if k in STACK_FIELDS}
    if type(value) in (list, tuple):
        return [_safe_value(v, depth + 1) for v in value[:100]]
    return "[omitted]"  # Don't call str/repr on requests, models or exceptions.


class EventFormatter(logging.Formatter):
    def __init__(self, style="text", service="eazyclass", environment="development"):
        super().__init__()
        self.output_style = style
        self.service = service
        self.environment = environment

    def format(self, record):
        data = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "service": self.service,
            "environment": self.environment,
            "message": record.getMessage(),
        }
        for key in sorted(CONTEXT_FIELDS):
            if key in record.__dict__:
                data[key] = _safe_value(record.__dict__[key])
        data.setdefault("event", "log.message")
        if record.exc_info and record.exc_info[1] is not None:
            data.update(safe_error_context(record.exc_info[1]))
        # Never use cached exc_text or stack_info: they may include source/secrets.
        if self.output_style == "json":
            return json.dumps(data, ensure_ascii=False, allow_nan=False)
        message = json.dumps(data.pop("message"), ensure_ascii=False)
        timestamp, level = data.pop("timestamp"), data.pop("level")
        logger_name = data.pop("logger")
        context = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, allow_nan=False)}"
            for key, value in data.items()
        )
        return f"{timestamp} [{level}] {logger_name}: {message} {context}"


def build_logging_config(*, debug=False, log_format=None, level="INFO",
                         service="eazyclass", environment=None):
    output_style = log_format or ("text" if debug else "json")
    if output_style not in {"text", "json"}:
        raise ValueError("LOG_FORMAT must be text or json")
    level = level.upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be DEBUG, INFO, WARNING, ERROR or CRITICAL")
    # Each hierarchy propagates to exactly one root handler. Third-party debug
    # logging is intentionally not enabled by the application's LOG_LEVEL.
    levels = {
        "scheduler": level, "utils": level, "scrapy_app": level,
        "schedule_spider": level, "eazyclass": level,
        "django": "INFO", "django.request": "ERROR", "django.server": "WARNING",
        "django.db.backends": "WARNING", "celery": "INFO", "celery.task": "INFO",
        "celery.redirected": "WARNING", "scrapy": "WARNING", "twisted": "WARNING",
        "httpx": "WARNING", "httpcore": "WARNING", "urllib3": "WARNING",
        "telebot": "WARNING", "py.warnings": "WARNING",
    }
    return {
        "version": 1, "disable_existing_loggers": False,
        "formatters": {"event": {
            "()": "eazyclass.logging_config.EventFormatter", "style": output_style,
            "service": service, "environment": environment or ("development" if debug else "production"),
        }},
        "handlers": {"console": {
            "class": "logging.StreamHandler", "formatter": "event",
            "filters": ["context"],
            "stream": "ext://sys.stderr",
        }},
        "filters": {"context": {"()": "eazyclass.logging_context.ContextFilter"}},
        "root": {"handlers": ["console"], "level": "WARNING"},
        "loggers": {name: {"handlers": [], "level": value, "propagate": True}
                    for name, value in levels.items()},
    }


def configure_service_logging(service=None, **kwargs):
    """Celery signal receiver and Scrapy child-process setup."""
    from django.conf import settings

    config = copy.deepcopy(settings.LOGGING)
    if service:
        config["formatters"]["event"]["service"] = service
    logging.config.dictConfig(config)
    logging.captureWarnings(True)
