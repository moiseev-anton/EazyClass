# from django.db.models import Model, Prefetch
# from .models import Lesson
# from django.core.exceptions import ObjectDoesNotExist

from django.core.cache import caches
from functools import wraps
from typing import Callable

DEFAULT_CACHE_TIMEOUT = 3600  # 1 час


def cache_data(key_template: str, timeout: int = DEFAULT_CACHE_TIMEOUT, cache_name: str = 'default') -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache = caches[cache_name]  # Получаем нужный кеш
            key = key_template.format(*args, **kwargs)  # Формируем ключ кеша
            cached_data = cache.get(key)
            if cached_data is not None:
                return cached_data
            result = func(*args, **kwargs)
            cache.set(key, result, timeout=timeout)
            return result

        return wrapper

    return decorator


def invalidate_cache(key_template: str, cache_name: str = 'default') -> Callable:
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)

            # Инвалидация кеша
            cache = caches[cache_name]
            key = key_template.format(*args, **kwargs)
            cache.delete(key)

            return result

        return wrapper

    return decorator


# def get_lessons_for_subscription(subscription_model: Model, subscription_id: int, dates: set):
#     try:
#         lessons_query = subscription_model.objects.prefetch_related(
#             Prefetch('lessons', queryset=Lesson.objects.filter(
#                 lesson_time__date__in=dates,
#                 is_active=True).select_related('subject', 'classroom', 'lesson_time', 'teacher'))
#         ).get(id=subscription_id)
#     except ObjectDoesNotExist:
#         return []
#
#     return [{
#         'date': lesson.lesson_time.date,
#         'time': lesson.lesson_time.start_time.strftime('%H:%M'),
#         'subject': lesson.subject.title,
#         'classroom': lesson.classroom.title,
#         'teacher': lesson.teacher.short_name if lesson.teacher else "Не указан"
#     } for lesson in lessons_query]
