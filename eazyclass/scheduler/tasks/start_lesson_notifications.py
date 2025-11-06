import logging
from datetime import datetime, timedelta

from celery import chain, shared_task
from django.conf import settings
from django.utils.timezone import make_aware, now

from scheduler.dtos import LessonSummary
from scheduler.models import Period, SocialAccount
from scheduler.notifications import TelegramNotifier
from scheduler.notifications.lesson_notification_service import LessonNotificationService
from scheduler.tasks.telegram_notification import send_admin_report

logger = logging.getLogger(__name__)


@shared_task(queue="periodic_tasks")
def schedule_lesson_notifications():
    today = now().date() + timedelta(days=1)
    periods = Period.objects.filter(date=today, start_time__isnull=False)

    for period in periods:
        run_time = make_aware(datetime.combine(period.date, period.start_time)) - timedelta(
            minutes=10
        )
        if run_time > now():

            chain(
                send_lesson_notifications.s(period.id),
                send_admin_report.s(),
            ).apply_async(eta=run_time)

            logger.info(f"Создана задача на {run_time} для периода {period}")


@shared_task(queue="notifications")
def send_lesson_notifications(period_id: int):
    try:
        try:
            period: Period = Period.objects.get(pk=period_id)
        except Period.DoesNotExist:
            logger.warning(f"Период {period_id} не найден — уведомления не будут отправлены.")
            raise

        notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
        notification_service = LessonNotificationService(notifier)
        summary: LessonSummary = notification_service.send_for_period(period)

        if blocked := summary.blocked_chat_ids:
            marked_count = SocialAccount.objects.mark_chats_blocked(blocked)
        logger.info(f"Отправлены уведомления для периода {period_id}")

        return summary.model_dump()
    except Exception as e:
        logger.error(e, exc_info=True)
