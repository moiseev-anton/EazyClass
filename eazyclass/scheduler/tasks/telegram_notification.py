import logging

from celery import shared_task
from django.conf import settings

from scheduler.notifications import TelegramMessagePreparer, TelegramNotifier

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0, default_retry_delay=60, queue="periodic_tasks")
def bulk_notification_telegram(self, update_summary):
    messages = TelegramMessagePreparer().prepare_notifications(update_summary)

    if not messages:
        logger.info("Нет уведомлений для рассылки — TelegramNotifier не создаётся.")
        return TelegramNotifier.empty_summary()

    notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
    sending_summary = notifier.send_batch(messages)
    return sending_summary
