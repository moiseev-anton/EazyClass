import json
import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.utils.timezone import make_aware, now
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from eazyclass.logging_config import safe_error_context

from scheduler.dtos import NotificationItem, PipelineSummary, StartNotificationSummary
from scheduler.dtos.summary_dtos.base_summary_dto import BaseSummary
from scheduler.models import Period, SocialAccount
from scheduler.models.social_account_model import Platform
from scheduler.notifications import NotificationService, TelegramNotifier

logger = logging.getLogger(__name__)


def send_upcoming_lesson_notifications(period_id: int):
    logger.info("Начинается подготовка рассылки о занятиях",
                extra={"event": "notification.preparing", "period_id": period_id})
    try:
        period: Period = Period.objects.get(pk=period_id)
        logger.info(
            "Определён период рассылки: %s",
            period,
            extra={"event": "notification.period_loaded", "period_id": period.pk},
        )

        notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
        notification_service = NotificationService(notifier)
        summary: StartNotificationSummary = notification_service.send_start_notifications(period)

        if blocked := summary.blocked_chat_ids:
            marked_count = SocialAccount.objects.mark_chats_blocked(platform=notifier.platform, chat_ids=blocked)

        return summary.model_dump()
    except Exception as e:
        logger.error("Подготовка или обработка результатов рассылки о занятиях завершилась ошибкой",
                     extra={"event": "notification.task_failed", "period_id": period_id, **safe_error_context(e)})
        raise


@shared_task(queue="notifications")
def process_upcoming_lesson_notification(period_id: int, periodic_task_id: int | None = None):
    try:
        summary = send_upcoming_lesson_notifications(period_id)
        send_admin_report(summary)
    finally:
        if periodic_task_id:
            PeriodicTask.objects.filter(id=periodic_task_id).delete()


@shared_task(queue="periodic_tasks")
def plan_upcoming_lesson_notifications():
    today = now().date()
    periods = Period.objects.filter(date=today, start_time__isnull=False)

    tasks_count = 0
    for period in periods:
        period_start = make_aware(datetime.combine(period.date, period.start_time))
        run_time = period_start - timedelta(minutes=10)
        if run_time <= now():
            continue

        run_hour = run_time.strftime("%H")  # e.g., '07'
        run_minute = run_time.strftime("%M")  # e.g., '50'

        crontab, created = CrontabSchedule.objects.get_or_create(
            minute=run_minute,
            hour=run_hour,
            day_of_month="*",
            month_of_year="*",
            day_of_week="*",
            timezone=settings.TIME_ZONE,
        )
        if created:
            logger.debug("Создано время запуска рассылки: %s:%s", run_hour, run_minute)

        task_name = f"Telegram-рассылка [{period}]"

        periodic_task, task_created = PeriodicTask.objects.get_or_create(
            name=task_name,
            defaults={
                "crontab": crontab,
                "task": process_upcoming_lesson_notification.name,
                "args": json.dumps([period.id]),
                "queue": "notifications",
                "one_off": True,
                "expire_seconds": 1800,
            },
        )

        periodic_task.args = json.dumps([period.id, periodic_task.id])
        periodic_task.save()

        if task_created:
            logger.debug("Создана одноразовая задача рассылки", extra={"period_id": period.id})
            tasks_count += 1

    logger.info("Запланировано %s новых задач рассылки", tasks_count,
                extra={"event": "notification.planned", "count": tasks_count})


# fmt: off
update_summary_test = {
    "added": [
        {"group_id": 5, "teacher_id": 7, "period_id": 934, "subject_id": 10},
        {"group_id": 6, "teacher_id": 5, "period_id": 945, "subject_id": 7},
    ],
    "updated": [
        {"group_id": 5, "teacher_id": 15, "period_id": 933, "subject_id": 10},
        {"group_id": 7, "teacher_id": 6, "period_id": 921, "subject_id": 7},
    ],
    "removed": [
        {"group_id": 5, "teacher_id": 15, "period_id": 923, "subject_id": 10},
        {"group_id": 5, "teacher_id": 11, "period_id": 913, "subject_id": 7},
    ],
}
# fmt: on


@shared_task(queue="periodic_tasks")
def send_lessons_refresh_notifications(summary_dict: dict) -> dict:
    logger.info("Начинается подготовка рассылки об изменении расписания",
                extra={"event": "notification.preparing"})
    pipeline_summary = PipelineSummary.deserialize(summary_dict)
    refreshed_lessons_summary = pipeline_summary.sync_summary

    notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
    service = NotificationService(notifier)
    notify_summary = service.send_refresh_notifications(refreshed_lessons_summary)

    if chat_ids := notify_summary.blocked_chat_ids:
        updated_count = SocialAccount.objects.mark_chats_blocked(
            platform=Platform.TELEGRAM, chat_ids=chat_ids
        )

    pipeline_summary.notification_summary = notify_summary
    return pipeline_summary.model_dump()


@shared_task(queue="periodic_tasks")
def send_admin_report(summary_dict: dict):
    """
    Финальная задача — отправка отчёта админу.
    Используем отдельный телеграм-бот для админов.
    Это работает пока в телеграм user_id == chat_id.
    Так как рассылка происходит по chat_id,
     а мы располагаем только chat_id для основного бота.
    """
    try:
        logger.info("Начинается подготовка отчёта администраторам",
                    extra={"event": "notification.admin_report.preparing"})
        summary = BaseSummary.deserialize(summary_dict)

        report_text = summary.to_message()
        staff_chat_ids = SocialAccount.objects.get_staff_chat_ids(platform=Platform.TELEGRAM)
        notification = NotificationItem(message=report_text, destinations=staff_chat_ids)

        notifier = TelegramNotifier(settings.TELEGRAM_ADMIN_BOT_TOKEN)
        notifier.send_notification(notification)
        return summary_dict
    except Exception as e:
        logger.error("Подготовка или отправка отчёта администраторам завершилась ошибкой",
                     extra={"event": "notification.admin_report.failed", **safe_error_context(e)})
        raise
