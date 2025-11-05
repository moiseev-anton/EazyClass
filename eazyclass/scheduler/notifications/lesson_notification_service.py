import logging
from collections import defaultdict
from typing import List, Set

from django.db.models import Prefetch

from scheduler.dtos import LessonSummary, NotificationItem
from scheduler.models import (
    GroupSubscription,
    Lesson,
    Period,
    SocialAccount,
    TeacherSubscription,
)
from scheduler.notifications import TelegramNotifier
from scheduler.notifications.utils import (
    format_group_lesson_message,
    format_teacher_lesson_message,
)

logger = logging.getLogger(__name__)


class LessonNotificationService:
    """
    Сервис для оркестрации уведомлений о уроках.
    Инкапсулирует логику запросов, группировки и отправки.
    """

    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self._platform = notifier.platform

    def _get_telegram_lessons(self, period: Period) -> List[Lesson]:
        """Получает уроки периода(пары) с prefetch подписок и аккаунтов."""
        account_prefetch = Prefetch(
            "user__accounts",
            queryset=SocialAccount.objects.filter(platform=self._platform, is_blocked=False),
            to_attr="telegram_accounts",
        )

        return list(
            Lesson.objects.filter(period=period)
            .select_related("group", "teacher", "subject", "classroom")
            .prefetch_related(
                Prefetch(
                    "group__subscriptions",
                    queryset=GroupSubscription.objects.filter(
                        user__accounts__platform=self._platform,
                        user__accounts__is_blocked=False,
                    )
                    .select_related("user")
                    .prefetch_related(account_prefetch),
                    to_attr="telegram_group_subscriptions",
                ),
                Prefetch(
                    "teacher__subscriptions",
                    queryset=TeacherSubscription.objects.filter(
                        user__accounts__platform=self._platform,
                        user__accounts__is_blocked=False,
                    )
                    .select_related("user")
                    .prefetch_related(account_prefetch),
                    to_attr="telegram_teacher_subscriptions",
                ),
            )
        )

    @staticmethod
    def _collect_group_notifications(lessons: List[Lesson]) -> List[NotificationItem]:
        """Собирает уведомления для групп (группировка уроков)."""
        lessons_by_group = defaultdict(list)
        for lesson in lessons:
            if lesson.group:
                lessons_by_group[lesson.group].append(lesson)

        notifications = []
        for group, group_lessons in lessons_by_group.items():
            chat_ids: Set[str] = set()
            for sub in getattr(group, "telegram_group_subscriptions", []):
                for acc in sub.user.telegram_accounts:
                    chat_ids.add(acc.chat_id)

            if chat_ids:
                message = format_group_lesson_message(group_lessons)
                notifications.append(NotificationItem(message, list(chat_ids)))
                logger.debug(f"Собрано {len(chat_ids)} чатов для группы {group.title}")

        return notifications

    @staticmethod
    def _collect_teacher_notifications(lessons: List[Lesson]) -> List[NotificationItem]:
        """Собирает уведомления для преподавателей (по одному на урок)."""
        notifications = []
        for lesson in lessons:
            if not lesson.teacher:
                continue

            chat_ids: Set[str] = set()
            for sub in getattr(lesson.teacher, "telegram_teacher_subscriptions", []):
                for acc in sub.user.telegram_accounts:
                    chat_ids.add(acc.chat_id)

            if chat_ids:
                message = format_teacher_lesson_message(lesson)
                notifications.append(NotificationItem(message, list(chat_ids)))
                logger.debug(
                    f"Собрано {len(chat_ids)} чатов для преподавателя {lesson.teacher.short_name}"
                )

        return notifications

    def send_for_period(self, period: Period) -> LessonSummary:
        """Основной метод: собирает и отправляет уведомления для периода"""
        summary = LessonSummary(period_str=str(period))

        lessons = self._get_telegram_lessons(period)
        if not lessons:
            logger.info(f"Нет уроков для уведомлений для периода {period}")
            return summary

        summary.lessons_count = len(lessons)

        notifications = self._collect_group_notifications(
            lessons
        ) + self._collect_teacher_notifications(lessons)

        if not notifications:
            logger.info(f"Нет подписчиков для уведомлений для периода {period}")
            return summary

        notify_summary = self.notifier.send_notifications(notifications)
        summary.merge_from(notify_summary)

        logger.info(f"Отправлено {summary.success_count} уведомлений для периода {period}")
        return summary
