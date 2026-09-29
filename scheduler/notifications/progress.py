"""Periodic snapshots, including while the sending thread waits for HTTP."""
import logging
from threading import Event, Lock, Thread
from time import monotonic

from eazyclass.logging_context import get_context

logger = logging.getLogger(__name__)


class DeliveryProgress:
    INTERVAL = 10.0
    STAGE_LABELS = {
        "checking_api": "ожидается ответ на проверку Telegram",
        "sending": "ожидается ответ на отправку",
        "retry_wait": "пауза перед повтором",
        "rate_limit_wait": "пауза по требованию Telegram",
        "rate_wait": "пауза ограничения частоты",
    }

    def __init__(self, notification_id, *, stage, total=None):
        self.context = {**get_context(), "notification_id": notification_id, "platform": "telegram"}
        self.started = monotonic()
        self.stage_started = self.started
        self.state = dict(stage=stage, planned_count=total, success_count=0, failed_count=0,
                          blocked_count=0, retry_count=0)
        self.wait_until = None
        self.lock = Lock()
        self.stop = Event()
        self.thread = Thread(target=self._run, name="notification-progress", daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.stop.set()
        self.thread.join()

    def update(self, *, stage=None, wait_seconds=None, **counts):
        with self.lock:
            self.state.update(counts)
            if stage is not None:
                self.state["stage"] = stage
                self.stage_started = monotonic()
                self.wait_until = None if wait_seconds is None else self.stage_started + wait_seconds

    def snapshot(self):
        with self.lock:
            now = monotonic()
            return {**self.context, **self.state,
                    "processed_count": self.state["success_count"] + self.state["failed_count"],
                    "duration_ms": round((now - self.started) * 1000, 3),
                    "stage_duration_ms": round((now - self.stage_started) * 1000, 3),
                    "retry_delay_seconds": round(max(0, self.wait_until - now), 1) if self.wait_until else 0}

    def _run(self):
        while not self.stop.wait(self.INTERVAL):
            self._log_snapshot(self.snapshot())

    def _log_snapshot(self, data):
        display = {
            **data,
            "stage_label": self.STAGE_LABELS.get(data["stage"], data["stage"]),
            "stage_seconds": data["stage_duration_ms"] / 1000,
            "elapsed_seconds": data["duration_ms"] / 1000,
        }
        if data["planned_count"] is None:
            message = (
                "Проверка Telegram: %(stage_label)s, этап %(stage_seconds).1f с; "
                "повторов %(retry_count)s; осталось паузы %(retry_delay_seconds).1f с; "
                "всего %(elapsed_seconds).1f с"
            )
        else:
            message = (
                "Telegram: обработано %(processed_count)s/%(planned_count)s; "
                "подтверждено %(success_count)s, не подтверждено %(failed_count)s "
                "(из них запрещено %(blocked_count)s); повторов %(retry_count)s; "
                "%(stage_label)s, этап %(stage_seconds).1f с, "
                "осталось паузы %(retry_delay_seconds).1f с; всего %(elapsed_seconds).1f с"
            )
        logger.info(message, display, extra={"event": "notification.progress", **data})
