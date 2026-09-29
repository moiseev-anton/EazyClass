import logging
from threading import Event, enumerate as threads
from unittest.mock import Mock

import pytest
import requests
from telebot.apihelper import ApiTelegramException

from eazyclass.logging_config import EventFormatter
from eazyclass.logging_context import logging_context
from scheduler.dtos import NotificationItem
from scheduler.notifications import telegram_notifier as module
from scheduler.notifications.progress import DeliveryProgress


def api_error(code, **parameters):
    return ApiTelegramException("sendMessage", Mock(status_code=code),
                                {"error_code": code, "description": "secret-response", "parameters": parameters})


@pytest.fixture
def bot(monkeypatch):
    bot = Mock()
    monkeypatch.setattr(module, "TeleBot", Mock(return_value=bot))
    monkeypatch.setattr(module.time, "sleep", Mock())
    return bot


def records(caplog, name):
    return [r for r in caplog.records if getattr(r, "event", "") == name]


def assert_no_reporter():
    assert not any(t.name == "notification-progress" for t in threads())


def test_success_counts_destinations_not_items_and_has_one_final(bot, caplog):
    caplog.set_level(logging.INFO)
    sender = module.TelegramNotifier("secret-token")
    result = sender.send_notifications(iter([NotificationItem("secret-message", [1, 2]),
                                            NotificationItem("secret-message", [1])]))
    assert result.success_count == 3
    assert bot.send_message.call_count == 3
    assert len(records(caplog, "notification.first_sent")) == 1
    final, = records(caplog, "notification.completed")
    assert final.planned_count == final.processed_count == final.success_count == 3
    assert final.outcome == "success"
    assert not records(caplog, "notification.progress")
    assert "secret" not in caplog.text
    assert_no_reporter()


@pytest.mark.parametrize("code,calls", [(400, 1), (401, 1), (403, 1), (429, 3), (500, 3)])
def test_retry_classification_and_safe_final_failure(bot, caplog, code, calls):
    caplog.set_level(logging.DEBUG)
    sender = module.TelegramNotifier("secret-token")
    bot.send_message.side_effect = api_error(code, retry_after=7)
    result = sender.send_notification(NotificationItem("secret-message", [123]))
    assert bot.send_message.call_count == calls
    assert result.failed_count == 1
    assert bool(result.blocked_chat_ids) == (code == 403)
    final, = records(caplog, "notification.completed")
    assert final.processed_count == 1 and final.retry_count == calls - 1
    assert final.outcome == "failed" and final.levelno == logging.ERROR
    if code == 429:
        assert [c.args[0] for c in module.time.sleep.call_args_list] == [7, 7, 7, .04]
    for record in caplog.records:
        for style in ("text", "text_verbose", "json"):
            assert "secret" not in EventFormatter(style=style).format(record)
    assert_no_reporter()


def test_timeout_then_success_does_not_count_retry_as_delivery(bot, caplog):
    caplog.set_level(logging.INFO)
    sender = module.TelegramNotifier("token")
    bot.send_message.side_effect = [requests.Timeout("secret-url"), None]
    result = sender.send_notification(NotificationItem("private", [1]))
    final, = records(caplog, "notification.completed")
    assert result.success_count == 1 and result.failed_count == 0
    assert final.retry_count == 1 and final.processed_count == 1


def test_repeated_failures_are_aggregated_at_info(bot, caplog):
    caplog.set_level(logging.INFO)
    sender = module.TelegramNotifier("token")
    bot.send_message.side_effect = [None] + [api_error(400)] * 100
    sender.send_notification(NotificationItem("private", list(range(101))))
    final, = records(caplog, "notification.completed")
    assert final.outcome == "partial" and final.api_failed_count == 100
    assert len(records(caplog, "notification.send_failed")) == 1


def test_empty_generator_is_skipped(bot, caplog):
    caplog.set_level(logging.INFO)
    module.TelegramNotifier("token").send_notifications(iter([]))
    assert records(caplog, "notification.completed")[0].outcome == "skipped"
    bot.send_message.assert_not_called()
    assert not records(caplog, "notification.first_sent")


@pytest.mark.parametrize("operation,stage", [("get_me", "checking_api"), ("send_message", "sending")])
def test_progress_runs_during_blocked_http_and_preserves_context(bot, monkeypatch, caplog, operation, stage):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(DeliveryProgress, "INTERVAL", .01)
    observed = Event()
    class Signal(logging.Handler):
        def emit(self, record):
            if getattr(record, "event", "") == "notification.progress":
                observed.set()
    handler = Signal()
    logger = logging.getLogger("scheduler.notifications.progress")
    logger.addHandler(handler)
    def blocked(**kwargs):
        assert observed.wait(2), "No progress while HTTP is blocked"
    getattr(bot, operation).side_effect = blocked
    try:
        with logging_context({"run_id": "test-run", "task_id": "test-task"}):
            sender = module.TelegramNotifier("token")
            if operation == "send_message":
                sender.send_notification(NotificationItem("private", [1]))
    finally:
        logger.removeHandler(handler)
    progress = records(caplog, "notification.progress")
    assert progress and progress[0].stage == stage
    assert progress[0].run_id == "test-run" and progress[0].task_id == "test-task"
    assert progress[0].processed_count == 0
    assert_no_reporter()


def test_permanent_readiness_failure_stops_reporter_and_does_not_send(bot, caplog):
    bot.get_me.side_effect = api_error(401)
    with pytest.raises(ApiTelegramException):
        module.TelegramNotifier("token")
    bot.get_me.assert_called_once()
    bot.send_message.assert_not_called()
    assert len(records(caplog, "notification.api_check_failed")) == 1
    assert "secret" not in caplog.text
    assert_no_reporter()


def test_interruption_stops_reporter_without_false_completion(bot, caplog):
    sender = module.TelegramNotifier("token")
    bot.send_message.side_effect = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        sender.send_notification(NotificationItem("private", [1]))
    assert not records(caplog, "notification.completed")
    assert records(caplog, "notification.interrupted")
    assert_no_reporter()


def test_readiness_retry_is_separate_from_delivery_retry_counts(bot, caplog):
    caplog.set_level(logging.INFO)
    bot.get_me.side_effect = [requests.ConnectionError("secret-url"), None]
    sender = module.TelegramNotifier("token")
    assert records(caplog, "notification.api_ready")[0].retry_count == 1
    sender.send_notification(NotificationItem("private", [1]))
    assert records(caplog, "notification.completed")[0].retry_count == 0


def test_readiness_budget_does_not_ignore_telegram_retry_after(bot, monkeypatch, caplog):
    monkeypatch.setattr(module.TelegramNotifier, "READY_RETRY_BUDGET", 5)
    bot.get_me.side_effect = api_error(429, retry_after=30)
    with pytest.raises(ApiTelegramException):
        module.TelegramNotifier("token")
    bot.get_me.assert_called_once()
    module.time.sleep.assert_not_called()
    assert_no_reporter()


def test_progress_during_retry_wait_has_remaining_delay(bot, monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(DeliveryProgress, "INTERVAL", .01)
    observed = Event()
    class Signal(logging.Handler):
        def emit(self, record):
            if getattr(record, "event", "") == "notification.progress" and record.stage == "retry_wait":
                observed.set()
    handler = Signal()
    logger = logging.getLogger("scheduler.notifications.progress")
    logger.addHandler(handler)
    def sleep(delay):
        if delay == 7:
            assert observed.wait(2)
    monkeypatch.setattr(module.time, "sleep", sleep)
    bot.send_message.side_effect = [api_error(429, retry_after=7), None]
    try:
        module.TelegramNotifier("token").send_notification(NotificationItem("private", [1]))
    finally:
        logger.removeHandler(handler)
    progress = records(caplog, "notification.progress")[0]
    assert progress.processed_count == 0 and progress.retry_count == 1
    assert 0 < progress.retry_delay_seconds <= 7
    assert_no_reporter()


def test_upcoming_task_failure_is_not_swallowed_and_cleans_schedule(monkeypatch):
    from scheduler.tasks import notification
    error = RuntimeError("private-error")
    monkeypatch.setattr(notification, "send_upcoming_lesson_notifications", Mock(side_effect=error))
    report = Mock()
    monkeypatch.setattr(notification, "send_admin_report", report)
    queryset = Mock()
    monkeypatch.setattr(notification.PeriodicTask.objects, "filter", Mock(return_value=queryset))
    with pytest.raises(RuntimeError) as raised:
        notification.process_upcoming_lesson_notification.run(42, periodic_task_id=7)
    assert raised.value is error
    report.assert_not_called()
    queryset.delete.assert_called_once()


def test_admin_report_error_propagates_without_logging_payload(monkeypatch, caplog):
    from scheduler.tasks import notification
    monkeypatch.setattr(notification.BaseSummary, "deserialize", Mock(side_effect=ValueError("secret-payload")))
    with pytest.raises(ValueError):
        notification.send_admin_report.run({"private": "secret-payload"})
    assert records(caplog, "notification.admin_report.failed")
    assert "secret-payload" not in caplog.text
