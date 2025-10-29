import logging
import time
from typing import Any, Dict

import requests
from telebot import TeleBot
from telebot.apihelper import ApiTelegramException
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    stop_after_delay,
    wait_exponential_jitter,
)

logger = logging.getLogger(__name__)


class TelegramNotifier:
    RATE_LIMIT = 25  # лимит Telegram API (до 30 msg/sec)

    def __init__(self, token: str):
        self.bot = TeleBot(token=token, parse_mode="HTML")
        self._interval = 1 / self.RATE_LIMIT
        self.delete_markup = InlineKeyboardMarkup()
        self.delete_markup.add(
            InlineKeyboardButton(text="Скрыть", callback_data="delete")
        )
        # counters
        self.blocked_chats = []
        self.success_count = 0
        self.failed_count = 0

        # проверка готовности API при старте
        try:
            self._wait_until_ready()
        except Exception as e:
            logger.warning(f"⚠️ Telegram API не готов после retry (60s): {e}.")
            raise

    def get_summary(self) -> Dict[str, Any]:
        """Возврат статистики рассылки."""
        return {
            "success": self.success_count,
            "failed": self.failed_count,
            "blocked": list(self.blocked_chats), # copy
        }

    def send_batch(self, notifications: list[dict[str, Any]]) -> dict[str, Any]:
        """Отправляет уведомления."""
        if not notifications:
            logger.info("Пустая коллекция уведомлений — отправка пропущена.")
            return self.get_summary()

        for item in notifications:
            message = item["message"]
            for tg_id in item["destinations"]:
                start_time = time.perf_counter()
                try:
                    self._safe_send_message(tg_id, message)
                except Exception as e:
                    logger.debug(f"❌ Уведомление для {tg_id} не отправлено: {e}")
                    self.failed_count += 1
                elapsed = time.perf_counter() - start_time
                time.sleep(max(0, self._interval - elapsed))

        logger.info(
            f"✅ Итоги рассылки: {self.success_count} успешно, "
            f"{self.failed_count} с ошибками, "
            f"{len(self.blocked_chats)} заблокировали."
        )
        return self.get_summary()

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential_jitter(initial=1, max=5),
        stop=stop_after_attempt(3),
        reraise=True,
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _safe_send_message(self, chat_id: int | str, text: str) -> None:
        """Отправляет сообщение"""
        try:
            self.bot.send_message(
                chat_id=chat_id, text=text, reply_markup=self.delete_markup
            )
            self.success_count += 1
            logger.debug(f"✅ Сообщение отправлено пользователю {chat_id}")

        except ApiTelegramException as e:
            status = getattr(e.result, "status_code", None)

            if status == 403:
                logger.warning(f"🚫 Пользователь {chat_id} заблокировал бота.")
                self.blocked_chats.append(chat_id)
                self.failed_count += 1
                # TODO: Добавить отражение блокировки чата в БД
                return

            elif status == 429:
                retry_after = (
                    e.result.get("parameters", {}).get("retry_after", 3)
                    if hasattr(e, "result")
                    else 3
                )
                logger.warning(f"⚠️ Rate limit для {chat_id}. Ждём {retry_after}s перед retry")
                time.sleep(retry_after)
                raise
            else:
                logger.warning(f"⚠️ API error {e.error_code} для {chat_id} — retry")
                raise
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"⚠️ Ошибка соединения с Telegram API: {e}")
            raise

    @retry(
        retry=retry_if_exception_type(Exception),
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_delay(60),
        reraise=True,
    )
    def _wait_until_ready(self):
        try:
            logger.debug("Проверка готовности Telegram API через get_me()")
            me = self.bot.get_me()
            logger.info(f"✅ Telegram API готов. Бот: {me.username}")
        except requests.exceptions.ConnectionError as e:
            logger.debug("DNS или соединение ещё не готовы, повтор...")
            raise

    @staticmethod
    def empty_summary() -> Dict[str, Any]:
        return {
            "success": 0,
            "failed": 0,
            "blocked": [],
        }
