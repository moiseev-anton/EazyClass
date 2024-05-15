from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from ..models import LessonTimeTemplate, LessonTime


@shared_task
def fill_lesson_times():
    today = timezone.now().date()
    end_date = today + timedelta(days=30)  # Заполнение на 30 дней вперед

    for single_date in (today + timedelta(n) for n in range((end_date - today).days + 1)):
        day_of_week = single_date.strftime('%A')
        templates = LessonTimeTemplate.objects.filter(day_of_week=day_of_week)
        for template in templates:
            LessonTime.objects.get_or_create(
                date=single_date,
                lesson_number=template.lesson_number,
                defaults={'start_time': template.start_time, 'end_time': template.end_time}
            )
    # TODO настроить логирование
    # logger.info(f"Данные о \"звонках\" успешно заполнены до {end_date}")


@shared_task
def apply_template_changes(start_date=None):
    if start_date is None:
        start_date = timezone.now().date()
    lessons_to_update = LessonTime.objects.filter(date__gte=start_date)
    for lesson in lessons_to_update:
        day_of_week = lesson.date.strftime('%A')
        try:
            template = LessonTimeTemplate.objects.get(day_of_week=day_of_week, lesson_number=lesson.lesson_number)
            lesson.start_time = template.start_time
            lesson.end_time = template.end_time
            lesson.save()
        except LessonTimeTemplate.DoesNotExist:
            continue
    # logger.info(f"Измененый шаблон \"звонков\" применен")

