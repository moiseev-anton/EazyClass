import logging
from typing import Any, Dict

from scheduler.dtos import NotificationSummary, StartNotificationSummary
from scheduler.models import (
    Lesson,
    Period,
)
from scheduler.notifications import collectors
from scheduler.notifications.telegram_notifier import TelegramNotifier

logger = logging.getLogger(__name__)


class NotificationService:
    """Сервис для оркестрации сборки и отправки уведомлений."""

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self._platform = notifier.platform

    def send_refresh_notifications(self, refresh_summary: Dict[str, Any]) -> NotificationSummary:
        """Cобирает и отправляет уведомления об изменении расписания"""
        notifications = collectors.collect_refresh_notifications(
            refresh_summary, platform=self._platform
        )

        if not notifications:
            return self.notifier.create_empty_summary()

        notify_summary = self.notifier.send_notifications(notifications)
        return notify_summary

    def send_start_notifications(self, period: Period) -> StartNotificationSummary:
        """Собирает и отправляет уведомления для периода"""
        summary = StartNotificationSummary(period_str=str(period))
        lessons = (
            Lesson.objects.filter(period=period)
            .select_related("group", "teacher", "subject", "classroom")
        )

        if not lessons:
            logger.info(f"Нет уроков для периода {period}")
            return summary

        notifications = collectors.collect_group_start(lessons, platform=self._platform)
        notifications += collectors.collect_teacher_start(lessons, platform=self._platform)

        if not notifications:
            logger.info(f"Нет подписчиков для уведомлений для периода {period}")
            return summary

        notify_summary = self.notifier.send_notifications(notifications)

        summary.lessons_count = len(lessons)
        summary.notifications_count = len(notifications)
        summary.merge_from(notify_summary)

        logger.info(f"Отправлено {summary.success_count} уведомлений для периода {period}")
        return summary
