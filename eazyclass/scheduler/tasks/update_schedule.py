import logging

from celery import chain, shared_task

from scheduler.tasks.run_schedule_spider import run_schedule_spider
from scheduler.tasks.sync_schedule import sync_schedule
from scheduler.tasks.telegram_notification import (
    send_admin_report,
    send_telegram_notifications,
)

logger = logging.getLogger(__name__)


# Цепочка: spider -> sync -> telegram_notifications
@shared_task(queue="periodic_tasks")
def update_schedule_pipeline():
    chain(
        run_schedule_spider.s(),
        sync_schedule.s(),
        send_telegram_notifications.s(),
        send_admin_report.s(),
    ).apply_async()
