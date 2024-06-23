from django.db.models import Model, Prefetch
from .models import Lesson
from django.core.exceptions import ObjectDoesNotExist


def get_lessons_for_subscription(subscription_model: Model, subscription_id: int, dates: set):
    try:
        lessons_query = subscription_model.objects.prefetch_related(
            Prefetch('lessons', queryset=Lesson.objects.filter(
                lesson_time__date__in=dates,
                is_active=True).select_related('subject', 'classroom', 'lesson_time', 'teacher'))
        ).get(id=subscription_id)
    except ObjectDoesNotExist:
        return []

    return [{
        'date': lesson.lesson_time.date,
        'time': lesson.lesson_time.start_time.strftime('%H:%M'),
        'subject': lesson.subject.title,
        'classroom': lesson.classroom.title,
        'teacher': lesson.teacher.short_name if lesson.teacher else "Не указан"
    } for lesson in lessons_query]

