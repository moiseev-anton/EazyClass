import logging
from dataclasses import asdict

from celery import shared_task
from django.conf import settings

from scheduler.models import Platform, SocialAccount
from scheduler.notifications import TelegramMessagePreparer, TelegramNotifier
from scheduler.notifications.types import NotificationItem
from scheduler.tasks.types import UpdatePipelineContext

logger = logging.getLogger(__name__)

update_summary_test = {
                    "added": [
                        {"group_id": 5, "teacher_id": 7, "period_id": 321, "subject_id": 10,},
                        {"group_id": 7, "teacher_id": 5, "period_id": 322, "subject_id": 7,},
                    ],
                    "updated": [
                        {"group_id": 6,"teacher_id": 15,"period_id": 321,"subject_id": 10,},
                        {"group_id": 2,"teacher_id": 6, "period_id": 322,"subject_id": 7,},
                    ],
                    "removed": [
                        {"group_id": 7,"teacher_id": 15,"period_id": 321,"subject_id": 10,},
                        {"group_id": 2,"teacher_id": 11,"period_id": 322,"subject_id": 7,},
                    ],
                }

@shared_task(bind=True, max_retries=0, default_retry_delay=60, queue="periodic_tasks")
def send_telegram_notifications(self, context_dict: dict) -> dict:
    context = UpdatePipelineContext(**context_dict)
    notifications = TelegramMessagePreparer.prepare_notifications(context.sync_summary)

    if not notifications:
        logger.info("Нет уведомлений для рассылки — TelegramNotifier не создаётся.")
        summary = TelegramNotifier.create_summary()
    else:
        notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
        summary = notifier.send_notifications(notifications)

    if chat_ids := summary.blocked_chat_ids:
        updated_count = SocialAccount.objects.mark_chats_blocked(
            platform=Platform.TELEGRAM, chat_ids=chat_ids
        )

    logger.info(f"Итоги рассылки: {summary}")
    context.notification_summary = summary.as_dict()
    return asdict(context)


@shared_task(bind=True, max_retries=0, queue="periodic_tasks")
def send_admin_report(self, context_dict: dict):
    """Финальная задача — отправка отчёта админу."""
    try:
        logger.info("Отправка отчёта админу...")
        context = UpdatePipelineContext(**context_dict)

        report_text =context.format_report()
        staff_chat_ids = SocialAccount.objects.get_staff_chat_ids(platform=Platform.TELEGRAM)
        notification = NotificationItem(message=report_text, destinations=staff_chat_ids)

        notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
        notifier.send_notification(notification)
        return context_dict
    except Exception as e:
        logger.error(e, exc_info=True)
