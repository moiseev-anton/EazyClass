import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Max
from django.utils import timezone

from ..models import LessonTime, LessonTimeTemplate

logger = logging.getLogger(__name__)


@shared_task(queue='periodic_tasks')
def fill_lesson_times():
    """
    Заполняет расписание уроков на текущий и следующий месяц, начиная с сегодняшней даты
    или следующего дня после последней заполненной даты и заканчивая последним днём следующего месяца.

    Обеспечивает периодическое заполнение расписания уроков актуальными данными из шаблона
    """
    today = timezone.now().date()
    next_month_start = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    end_date = (next_month_start + timedelta(days=31)).replace(day=1) - timedelta(days=1)

    # Получаем максимальную дату в таблице LessonTime
    max_date = LessonTime.objects.aggregate(max_date=Max('date'))['max_date']

    # Устанавливаем начальную дату
    if max_date:
        start_date = max_date + timedelta(days=1)
    else:
        start_date = today - timedelta(days=1)

    # Проверяем, нужно ли выполнять заполнение
    if start_date <= end_date:
        for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days + 1)):
            day_of_week = single_date.strftime('%A')
            templates = LessonTimeTemplate.objects.filter(day_of_week=day_of_week)
            for template in templates:
                LessonTime.objects.get_or_create(
                    date=single_date,
                    lesson_number=template.lesson_number,
                    defaults={'start_time': template.start_time, 'end_time': template.end_time}
                )

    # Логгирование или уведомление об успешном завершении
    logger.info(f"Расписание звонков заполнены на период {start_date} - {end_date}.")
