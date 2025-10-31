import logging
import time
from typing import Iterable

import requests
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
)

from scheduler.notifications.exceptions import ChatBlocked, should_retry
from scheduler.notifications.types import NotificationItem, NotificationSummary

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Класс-обёртка для отправки уведомлений через Telegram Bot API.

    Использует библиотеку `telebot` для взаимодействия с Telegram API и
    обеспечивает централизованную обработку ошибок, таких как блокировка бота
    пользователем или превышение лимитов запросов (ошибка 429).

    Экземпляры класса не требуют явного закрытия: сессии HTTP создаются и
    управляются библиотекой TeleBot автоматически.
    """

    RATE_LIMIT = 25  # лимит Telegram API (до 30 msg/sec)

    def __init__(self, bot_token: str, rate_limit: int = RATE_LIMIT):
        self.bot = TeleBot(token=bot_token, parse_mode="HTML")
        self._interval = 1 / rate_limit if rate_limit else 0
        self.markup = self._create_message_markup()

        # проверка готовности API при старте
        try:
            self._ensure_api_ready()
        except Exception as e:
            logger.warning(f"⚠️ Telegram API не готов после retry (60s): {e}.")
            raise

    @retry(
        retry=retry_if_exception(should_retry),
        wait=wait_exponential_jitter(initial=1, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def send_message(self, text: str, chat_id: int | str) -> None:
        try:
            self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=self.markup
            )
            logger.debug(f"✅ Сообщение отправлено пользователю {chat_id}")

        except ApiTelegramException as e:
            status = getattr(e.result, "status_code", None)
            match status:
                case 403:
                    warning_text = f"🚫 Пользователь {chat_id} заблокировал бота."
                    logger.warning(warning_text)
                    raise ChatBlocked(warning_text)
                case 429:
                    retry_after = (
                        e.result.get("parameters", {}).get("retry_after", 3)
                        if hasattr(e, "result")
                        else 3
                    )
                    time.sleep(retry_after)
                    raise
                case _:
                    raise

    def send_notifications(self, notifications: Iterable[NotificationItem]) -> NotificationSummary:
        """
        Отправляет коллекцию NotificationItem — каждый элемент может содержать
        одно сообщение и несколько получателей.
        """
        summary = self.create_summary()
        if not notifications:
            logger.info("Пустая коллекция уведомлений — отправка пропущена.")
            return summary

        logger.info(notifications)
        for item in notifications:
            text = item.message
            for chat_id in item.destinations:
                start_time = time.perf_counter()

                try:
                    self.send_message(text=text, chat_id=chat_id)
                    summary.success_count += 1
                except ChatBlocked:
                    summary.failed_count += 1
                    summary.blocked_chat_ids.add(chat_id)
                except Exception:
                    summary.failed_count += 1

                elapsed = time.perf_counter() - start_time
                time.sleep(max(0, self._interval - elapsed))

        return summary

    def send_notification(self, notification: NotificationItem) -> NotificationSummary:
        """Отправляет одно уведомление (одно сообщение для нескольких получателей)."""
        return self.send_notifications(notifications=(notification,))

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_delay(60),
        reraise=True,
    )
    def _ensure_api_ready(self):
        """Ожидает готовности Telegram API к работе."""
        try:
            logger.debug("Проверка готовности Telegram API через get_me()")
            me = self.bot.get_me()
            logger.info(f"✅ Telegram API готов. Бот: {me.username}")
        except requests.exceptions.ConnectionError as e:
            logger.debug("DNS или соединение ещё не готовы, повтор...")
            raise

    @staticmethod
    def _create_message_markup() -> InlineKeyboardMarkup:
        """Создаёт стандартную клавиатуру для сообщений."""
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton(text="Скрыть", callback_data="delete")
        )
        return markup

    @classmethod
    def create_summary(cls) -> NotificationSummary:
        return NotificationSummary()
