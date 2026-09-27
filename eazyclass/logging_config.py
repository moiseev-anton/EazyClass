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
    "groups_count", "parsed_count", "unchanged_count", "pending_count", "lessons_count", "stage",
    "request_attempt",
    "faculties_count", "deactivated_faculties_count", "deactivated_groups_count", "unmatched_count",
})
STACK_FIELDS = frozenset({"error_type", "frames", "file", "line", "function"})


class CeleryEventFilter(logging.Filter):
    """Keep routine task bookkeeping on DEBUG and never print result payloads."""
    def __init__(self):
        super().__init__()
        from celery.app import trace
        self.events = {
            trace.LOG_RECEIVED: ("celery.task.received", "Задача получена", True),
            trace.LOG_SUCCESS: ("celery.task.completed", "Задача выполнена", True),
            trace.LOG_RETRY: ("celery.task.retry", "Запрошен повтор задачи", False),
            trace.LOG_FAILURE: ("celery.task.failed", "Задача завершилась ошибкой", False),
            trace.LOG_REJECTED: ("celery.task.rejected", "Задача отклонена", False),
            trace.LOG_IGNORED: ("celery.task.ignored", "Задача пропущена", False),
        }

    def filter(self, record):
        if record.name not in {"celery.app.trace", "celery.worker.strategy"}:
            return True
        event = self.events.get(record.msg) if isinstance(record.msg, str) else None
        payload = getattr(record, "data", None)
        if event is None or not isinstance(payload, dict):
            return True
        event_name, message, routine = event
        if routine:
            if not logging.getLogger("scheduler").isEnabledFor(logging.DEBUG):
                return False
            record.levelno, record.levelname = logging.DEBUG, "DEBUG"
        record.event = event_name
        record.task_id = payload.get("id")
        record.task_name = payload.get("name")
        record.msg = message + ": %s"
        record.args = (str(record.task_name).rsplit(".", 1)[-1],)
        record.__dict__.pop("data", None)
        return True


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
        if self.output_style == "text":
            return self._compact_text(data)
        message = json.dumps(data.pop("message"), ensure_ascii=False)
        timestamp, level = data.pop("timestamp"), data.pop("level")
        logger_name = data.pop("logger")
        context = " ".join(
            f"{key}={json.dumps(value, ensure_ascii=False, allow_nan=False)}"
            for key, value in data.items()
        )
        return f"{timestamp} [{level}] {logger_name}: {message} {context}"

    @staticmethod
    def _compact_text(data):
        # Local reading: message first. Full identifiers/metadata remain available
        # in JSON and text_verbose; shortened references aren't unique identifiers.
        message = json.dumps(data["message"], ensure_ascii=False)[1:-1]
        details = []
        for field, label in (("run_id", "run"), ("request_id", "req")):
            if data.get(field):
                short_id = json.dumps(str(data[field])[:8], ensure_ascii=False)[1:-1]
                details.append(f"{label}={short_id}")
                break
        for field in ("user_id", "group_id", "period_id", "method", "route", "status_code", "duration_ms"):
            if field in data:
                details.append(f"{field}={json.dumps(data[field], ensure_ascii=False)}")
        if type(data.get("attempt")) is int and data["attempt"] > 1:
            details.append(f"attempt={data['attempt']}")
        if data.get("error_stack"):
            errors = []
            for item in data["error_stack"] if isinstance(data["error_stack"], list) else []:
                if not isinstance(item, dict):
                    continue
                frames = item.get("frames", [])
                location = frames[-1] if isinstance(frames, list) and frames and isinstance(frames[-1], dict) else {}
                errors.append("%s@%s:%s(%s)" % (
                    item.get("error_type"), location.get("file", "?"),
                    location.get("line", "?"), location.get("function", "?"),
                ))
            # JSON-escape metadata as well, so external strings can't add lines.
            details.append(json.dumps(" <- ".join(errors), ensure_ascii=False)[1:-1])
        elif data.get("error_type"):
            details.append(json.dumps(data["error_type"], ensure_ascii=False))
        suffix = " | " + " ".join(details) if details else ""
        return f"{data['timestamp'][11:23]} [{data['level']}] {message}{suffix}"


def build_logging_config(*, debug=False, log_format=None, level=None,
                         service="eazyclass", environment=None):
    output_style = log_format or ("text" if debug else "json")
    if output_style not in {"text", "text_verbose", "json"}:
        raise ValueError("LOG_FORMAT must be text, text_verbose or json")
    level = (level or ("DEBUG" if debug else "INFO")).upper()
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
            "filters": ["context", "celery_events"],
            "stream": "ext://sys.stderr",
        }},
        "filters": {
            "context": {"()": "eazyclass.logging_context.ContextFilter"},
            "celery_events": {"()": "eazyclass.logging_config.CeleryEventFilter"},
        },
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
