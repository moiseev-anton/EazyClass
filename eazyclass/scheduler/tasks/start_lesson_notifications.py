import json
import logging
from datetime import datetime, timedelta

from celery import chain, shared_task
from django.conf import settings
from django.utils.timezone import make_aware, now
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from scheduler.dtos import LessonSummary
from scheduler.models import Period, SocialAccount
from scheduler.notifications import TelegramNotifier
from scheduler.notifications.lesson_notification_service import LessonNotificationService
from scheduler.tasks.telegram_notification import send_admin_report

logger = logging.getLogger(__name__)


@shared_task(queue="notifications")
def telegram_start_lesson_notifications(period_id: int):
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


@shared_task(queue="notifications")
def send_lesson_and_report(period_id: int, periodic_task_id: int | None = None):
    try:
        chain(
            telegram_start_lesson_notifications.s(period_id),
            send_admin_report.s(),
        ).delay()
    except Exception as e:
        logger.error(f"Ошибка в цепочке рассылки для {period_id}: {e}", exc_info=True)
    finally:
        if periodic_task_id:
            PeriodicTask.objects.filter(id=periodic_task_id).delete()


@shared_task(queue="periodic_tasks")
def schedule_lesson_notifications():
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
            logger.info(f"Создан новый CrontabSchedule: {run_hour}:{run_minute}")

        task_name = f"Telegram-рассылка [{period}]"

        periodic_task, task_created = PeriodicTask.objects.get_or_create(
            name=task_name,
            defaults={
                "crontab": crontab,
                "task": send_lesson_and_report.name,
                "args": json.dumps([period.id]),
                "queue": "notifications",
                "one_off": True,
                "expire_seconds": 1800,
            },
        )

        periodic_task.args = json.dumps([period.id, periodic_task.id])
        periodic_task.save()

        if task_created:
            logger.info(f'Создана одноразовая задача "{task_name}"')
            tasks_count += 1


    logger.info(f"Создано {tasks_count} задач для Telegram-рассылки")
