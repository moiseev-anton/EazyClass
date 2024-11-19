import logging
from datetime import datetime, timedelta

from django.core.cache import caches
from telebot.types import User as TelegramUser

from ..scheduler.models import User

cache = caches['telegrambot_cache']
logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 86400  # 24 часа


# def sign_up_user(telegram_user: TelegramUser):
#     # Создаем или получаем пользователя в БД
#     user, created = User.objects.get_or_create(
#         telegram_id=str(telegram_user.id),
#         defaults={
#             'first_name': telegram_user.first_name,
#             'last_name': telegram_user.last_name or '',
#             'is_active': True
#         }
#     )
#     cache_user_data(user)
#
#     return created


# def cache_user_data(telegram_id: int) -> dict:
#     try:
#         cache_key = f"user_data_{telegram_id}"
#         user = User.objects.get(telegram_id=telegram_id)
#         user_data = user.to_dict()
#         cache.set(cache_key, user_data, timeout=CACHE_TIMEOUT)
#         return user_data
#     except Exception as e:
#         logger.warning(f'Ошибка кеширования данных пользователя: {str(e)}')
#         raise  # Нет пользователя в БД


# def get_cached_user_data(telegram_id: int) -> dict:
#     """
#     Кеширует данные пользователя, используя его telegram_id как ключ.
#     Если данные в кеше отсутствуют, загружает их из базы данных и затем кеширует.
#
#     Args:
#         telegram_id (str): Telegram ID пользователя.
#
#     Returns:
#         dict: Словарь с данными пользователя.
#     """
#     cache_key = f"user_data_{telegram_id}"
#     user_data = cache.get(cache_key)
#
#     if not user_data:
#         try:
            # user_data = cache_user_data(telegram_id)
    #     except User.DoesNotExist as e:
    #         logger.warning(f'Ошибка получения пользователя из БД: {str(e)}')
    #         raise
    # return user_data


def get_date_range(request_type):
    today = datetime.now().date()
    if request_type == 'today':
        return today, today
    elif request_type == 'tomorrow':
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow
    elif request_type == 'from_today':
        end = today + timedelta(days=6)
        return today, end
    elif request_type == 'week':
        start_week = today - timedelta(days=today.weekday())
        end_week = start_week + timedelta(days=6)
        return today, end_week


def get_schedule_for_dates(start_date, end_date, group_id=None, teacher_id=None):
    lessons = Lesson.objects.filter(
        lesson_time__date__range=(start_date, end_date),
        group_id=group_id,  # или teacher_id=teacher_id, если по учителю
        is_active=True
    ).select_related('subject', 'teacher', 'classroom').order_by('lesson_time__date', 'lesson_time__start_time')

    schedule_info = []
    for lesson in lessons:
        day_info = f"{lesson.lesson_time.date.strftime('%Y-%m-%d')}: {lesson.subject.title} с {lesson.teacher.short_name} в {lesson.classroom.title}"
        schedule_info.append(day_info)

    return "\n".join(schedule_info) if schedule_info else "Расписания на выбранный период нет."

def cache_subscription(user):
    cache_key = f"user_subscription_{user.telegram_id}"
    if user.subscription:
        subscription_data = {
            'type': user.content_type.model,
            'id': user.object_id,
            'name': user.subscription.title if hasattr(user.subscription, 'title') else user.subscription.short_name
        }
        cache.set(cache_key, subscription_data, timeout=86400)  # Кешируем на 24 часа
    else:
        # Устанавливаем специальное значение, указывающее на отсутствие подписки
        subscription_data = "no_subscription"
        cache.set(cache_key, subscription_data, timeout=86400)

    return subscription_data


# def get_cached_subscription(telegram_id):
#     cache_key = f"user_subscription_{telegram_id}"
#     subscription_data = cache.get(cache_key)
#
#     if subscription_data is None:
#         # Подписка не найдена в кэше, получаем её из БД
#         user = User.objects.get(telegram_id=str(telegram_id))
#         subscription_data = cache_subscription(user)  # Кешируем и получаем данные подписки
#
#     if subscription_data == "no_subscription":
#         # Подтверждаем, что подписка действительно отсутствует
#         subscription_data = None
#
#     return subscription_data
