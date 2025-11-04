import logging
from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Prefetch
from django.utils.timezone import make_aware, now

from scheduler.models import GroupSubscription, Lesson, Period, Platform, SocialAccount, TeacherSubscription
from scheduler.notifications import TelegramNotifier
from scheduler.notifications.types import NotificationItem

logger = logging.getLogger(__name__)


# — ➖ ▪️🔹▫️◾️🔘 🎓

def format_start_lesson_text(lesson: Lesson) -> str:
    number = f"{lesson.period.lesson_number}\ufe0f\u20e3"
    start_time = lesson.period.start_time.strftime('%H:%M')

    group_info = lesson.group.title
    if lesson.subgroup and lesson.subgroup != "0":
        group_info += f" ({lesson.subgroup} подгруппа)"

    return (
        "Предстоящее занятие 📚\n"
        "<blockquote>"
        f"{number} {start_time}  📍 {lesson.classroom.title}\n"
        f"<b>{lesson.subject.title}</b>\n"
        f"— <i>{lesson.teacher.short_name}</i>\n"
        f"— <i>{group_info}</i>"
        "</blockquote>"
    )


@shared_task(queue='periodic_tasks')
def schedule_lesson_notifications():
    today = now().date()
    periods = Period.objects.filter(date=today, start_time__isnull=False)

    for period in periods:
        run_time = make_aware(datetime.combine(period.date, period.start_time)) - timedelta(minutes=10)
        if run_time > now():
            send_lesson_notifications.apply_async(
                args=(period.id,),
                eta=run_time
            )
            logger.info(f"Создана задача на {run_time} для периода {period.id}")


@shared_task(queue='notifications')
def send_lesson_notifications(period_id: int):
    try:
        try:
            period: Period = Period.objects.get(pk=period_id)
        except Period.DoesNotExist:
            logger.warning(f"Период {period_id} не найден — уведомления не будут отправлены.")
            return

        account_prefetch = Prefetch(
                            "user__accounts",
                            queryset=SocialAccount.objects.filter(
                                platform=Platform.TELEGRAM,
                                is_blocked=False,
                            )
                        )

        lessons = (
            Lesson.objects
            .filter(period=period)
            .select_related("group", "teacher", "subject", "classroom")
            .prefetch_related(
                Prefetch(
                    "group__subscriptions",
                    queryset=GroupSubscription.objects.filter(
                        user__accounts__platform=Platform.TELEGRAM,
                        user__accounts__is_blocked=False,
                    )
                    .select_related("user")
                    .prefetch_related(account_prefetch),
                    to_attr="telegram_group_subscriptions"
                ),
                Prefetch(
                    "teacher__subscriptions",
                    queryset=TeacherSubscription.objects.filter(
                        user__accounts__platform=Platform.TELEGRAM,
                        user__accounts__is_blocked=False,
                    )
                    .select_related("user")
                    .prefetch_related(account_prefetch),
                    to_attr="telegram_teacher_subscriptions"
                )
            )
        )

        notifications = []
        # Теперь можно подготовить и отправить уведомления
        for lesson in lessons:
            chat_ids = set()
            for sub in getattr(lesson.group, "telegram_group_subscriptions", []):
                for acc in sub.user.accounts.all():
                    chat_ids.add(acc.chat_id)
            for sub in getattr(lesson.teacher, "telegram_teacher_subscriptions", []):
                for acc in sub.user.accounts.all():
                    chat_ids.add(acc.chat_id)

            if chat_ids:
                message = format_start_lesson_text(lesson)
                notif = NotificationItem(message, list(chat_ids))
                notifications.append(notif)

        if notifications:
            notifier = TelegramNotifier(settings.TELEGRAM_BOT_TOKEN)
            summary = notifier.send_notifications(notifications)
            if blocked := summary.blocked_chat_ids:
                marked_count = SocialAccount.objects.mark_chats_blocked(blocked)
            logger.info(f"Отправлены уведомления для периода {period_id}")

    except Exception as e:
        logger.error(e,exc_info=True)
