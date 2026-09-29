import logging
import random
import time
from typing import Iterable
from uuid import uuid4

from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup

from eazyclass.logging_config import safe_error_context
from scheduler.dtos import NotificationItem, NotificationSummary
from scheduler.models.social_account_model import Platform, PlatformValue
from scheduler.notifications.exceptions import ChatBlocked, failure_reason, should_retry
from scheduler.notifications.progress import DeliveryProgress

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sequential Telegram sender; one instance per notification operation."""

    _PLATFORM: PlatformValue = Platform.TELEGRAM.value
    RATE_LIMIT = 25  # лимит Telegram API (до 30 msg/sec)
    READY_RETRY_BUDGET = 60

    def __init__(self, bot_token: str, rate_limit: int = RATE_LIMIT):
        self.notification_id = str(uuid4())
        self.bot = TeleBot(token=bot_token, parse_mode="HTML")
        self._interval = 1 / rate_limit if rate_limit else 0
        self.markup = self._create_message_markup()
        self._progress = None
        self._retry_count = 0
        self._warned = set()
        self._ensure_api_ready()

    def _log_problem(self, exc, *, event, message, **extra):
        reason = failure_reason(exc)
        status = getattr(exc, "error_code", None)
        if isinstance(exc, ChatBlocked):
            status = 403
        if status is None:
            status = getattr(getattr(exc, "result", None), "status_code", None)
        # Bound warning volume per category; repeats remain available on DEBUG.
        key = (event, reason, status)
        level = logging.DEBUG if key in self._warned else logging.WARNING
        self._warned.add(key)
        logger.log(level, message, extra={"event": event, "reason": reason,
                   "notification_id": self.notification_id, "status_code": status,
                   **safe_error_context(exc), **extra})

    def _retry_delay(self, exc, attempt):
        if isinstance(exc, ApiTelegramException) and exc.error_code == 429:
            value = exc.result_json.get("parameters", {}).get("retry_after", 3)
            if isinstance(value, (int, float)) and value >= 0:
                return value
            return 3
        return min(2 ** (attempt - 1) + random.uniform(0, 1), 5)

    def _wait_for_retry(self, exc, attempt, delay):
        self._retry_count += 1
        if self._progress:
            self._progress.update(stage="retry_wait", wait_seconds=delay, retry_count=self._retry_count)
        self._log_problem(
            exc, event="notification.retry_requested",
            message=f"Временный сбой Telegram; повтор после попытки {attempt} через {delay:.1f} с",
            request_attempt=attempt, retry_delay_seconds=delay,
        )
        time.sleep(delay)

    def _ensure_api_ready(self):
        logger.info("Проверяется доступность Telegram API",
                    extra={"event": "notification.api_check_started", "notification_id": self.notification_id})
        with DeliveryProgress(self.notification_id, stage="checking_api") as progress:
            self._progress = progress
            deadline = time.monotonic() + self.READY_RETRY_BUDGET
            attempt = 0
            try:
                while True:
                    attempt += 1
                    progress.update(stage="checking_api", request_attempt=attempt)
                    try:
                        self.bot.get_me()
                        break
                    except Exception as exc:
                        delay = self._retry_delay(exc, attempt)
                        if not should_retry(exc) or time.monotonic() + delay >= deadline:
                            raise
                        self._wait_for_retry(exc, attempt, delay)
            except Exception as exc:
                progress.close()
                logger.error("Проверка Telegram API завершилась ошибкой",
                             extra={"event": "notification.api_check_failed", **progress.snapshot(),
                                    "outcome": "failed", "reason": failure_reason(exc), **safe_error_context(exc)})
                raise
            finally:
                self._progress = None
        logger.info("Telegram API успешно ответил на проверку",
                    extra={"event": "notification.api_ready", **progress.snapshot()})

    def send_message(self, text: str, chat_id: int | str) -> None:
        for attempt in range(1, 4):
            if self._progress:
                self._progress.update(stage="sending", request_attempt=attempt)
            try:
                self.bot.send_message(chat_id=chat_id, text=text)
                logger.debug("Telegram подтвердил отправку сообщения",
                             extra={"event": "notification.message_sent", "notification_id": self.notification_id,
                                    "recipient_id": chat_id})
                return
            except ApiTelegramException as exc:
                if exc.error_code == 403:
                    raise ChatBlocked("Telegram forbids sending to this chat") from exc
                if attempt == 3 or not should_retry(exc):
                    if exc.error_code == 429:
                        # Even with no attempts left, do not send to the next chat
                        # before Telegram's requested cooldown has elapsed.
                        delay = self._retry_delay(exc, attempt)
                        if self._progress:
                            self._progress.update(stage="rate_limit_wait", wait_seconds=delay)
                        self._log_problem(exc, event="notification.rate_limited",
                                          message=f"Telegram ограничил отправку; пауза {delay:.1f} с перед продолжением рассылки",
                                          retry_delay_seconds=delay)
                        time.sleep(delay)
                    raise
                self._wait_for_retry(exc, attempt, self._retry_delay(exc, attempt))
            except Exception as exc:
                if attempt == 3 or not should_retry(exc):
                    raise
                self._wait_for_retry(exc, attempt, self._retry_delay(exc, attempt))

    def send_notifications(self, notifications: Iterable[NotificationItem]) -> NotificationSummary:
        notifications = list(notifications)
        total = sum(len(item.destinations) for item in notifications)
        summary = self.create_empty_summary()
        failure_counts = dict(network_failed_count=0, api_failed_count=0, other_failed_count=0)
        self._retry_count = 0
        self._warned.clear()
        logger.info("Начинается отправка: запланировано %s сообщений", total,
                    extra={"event": "notification.sending_started", "planned_count": total,
                           "notification_id": self.notification_id})
        with DeliveryProgress(self.notification_id, stage="sending", total=total) as progress:
            self._progress = progress
            try:
                for item in notifications:
                    for chat_id in item.destinations:
                        try:
                            self.send_message(text=item.message, chat_id=chat_id)
                            summary.success_count += 1
                            if summary.success_count == 1:
                                logger.info("Telegram подтвердил первую отправку",
                                            extra={"event": "notification.first_sent", "notification_id": self.notification_id})
                        except ChatBlocked as exc:
                            summary.failed_count += 1
                            summary.blocked_chat_ids.append(chat_id)
                            self._log_problem(exc, event="notification.send_failed",
                                              message="Telegram запретил отправку адресату", recipient_id=chat_id)
                        except Exception as exc:
                            summary.failed_count += 1
                            reason = failure_reason(exc)
                            if reason in {"timeout", "connection_error"}:
                                category = "network_failed_count"
                            elif reason in {"api_error", "http_error", "rate_limited"}:
                                category = "api_failed_count"
                            else:
                                category = "other_failed_count"
                            failure_counts[category] += 1
                            self._log_problem(exc, event="notification.send_failed",
                                              message="Отправка сообщения не подтверждена после доступных попыток", recipient_id=chat_id)
                        progress.update(stage="rate_wait", success_count=summary.success_count,
                                        failed_count=summary.failed_count, blocked_count=len(summary.blocked_chat_ids),
                                        **failure_counts)
                        time.sleep(self._interval)
            except BaseException as exc:
                progress.close()
                logger.error("Рассылка прервана до обработки всех сообщений",
                             extra={"event": "notification.interrupted", **progress.snapshot(),
                                    "outcome": "failed", **safe_error_context(exc)})
                raise
            finally:
                self._progress = None
        if not total:
            outcome, level = "skipped", logging.INFO
        elif not summary.failed_count:
            outcome, level = "success", logging.INFO
        elif summary.success_count:
            outcome, level = "partial", logging.WARNING
        else:
            outcome, level = "failed", logging.ERROR
        final = progress.snapshot()
        final.update(failure_counts)
        logger.log(
            level,
            "Рассылка завершена: подтверждено %(success_count)s/%(planned_count)s, "
            "не подтверждено %(failed_count)s (запрещено %(blocked_count)s, "
            "сеть %(network_failed_count)s, API %(api_failed_count)s, прочие %(other_failed_count)s), "
            "повторов %(retry_count)s; %(elapsed_seconds).1f с",
            {**final, "elapsed_seconds": final["duration_ms"] / 1000},
            extra={"event": "notification.completed", **final, "outcome": outcome},
        )
        return summary

    def send_notification(self, notification: NotificationItem) -> NotificationSummary:
        return self.send_notifications((notification,))

    @staticmethod
    def _create_message_markup() -> InlineKeyboardMarkup:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton(text="Скрыть", callback_data="delete"))
        return markup

    @classmethod
    def create_empty_summary(cls) -> NotificationSummary:
        return NotificationSummary()

    @property
    def platform(self) -> PlatformValue:
        return self._PLATFORM
