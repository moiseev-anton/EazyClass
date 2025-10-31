import logging

from celery import shared_task
from django.conf import settings

from scheduler.models import Platform, SocialAccount
from scheduler.notifications import TelegramMessagePreparer, TelegramNotifier
from scheduler.notifications.types import NotificationSummary

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0, default_retry_delay=60, queue="periodic_tasks")
def bulk_notification_telegram(self, update_summary) -> NotificationSummary:
    notifications = TelegramMessagePreparer.prepare_notifications(update_summary)

    if not notifications:
        logger.info("Нет уведомлений для рассылки — TelegramNotifier не создаётся.")
        return TelegramNotifier.create_summary()

    notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
    summary = notifier.send_notifications(notifications)

    if chat_ids := summary.blocked_chat_ids:
        updated_count = SocialAccount.objects.mark_chats_blocked(
            platform=Platform.TELEGRAM, chat_ids=chat_ids
        )

    return summary
