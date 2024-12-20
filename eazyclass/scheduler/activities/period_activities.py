from datetime import datetime, timedelta
from datetime import time
import dateparser

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from scheduler.models import Period, PeriodTemplate

DEFAULT_PERIOD_TEMPLATE = {
    ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'): [
        ('1', time(8, 0), time(9, 35)),
        ('2', time(9, 45), time(11, 20)),
        ('3', time(12, 20), time(13, 55)),
        ('4', time(14, 5), time(15, 40)),
        ('5', time(15, 50), time(17, 25)),
        ('6', time(17, 35), time(19, 10)),
    ],
    ('Saturday',): [
        ('1', time(8, 0), time(9, 35)),
        ('2', time(9, 45), time(11, 20)),
        ('3', time(11, 50), time(13, 25)),
        ('4', time(13, 35), time(15, 10)),
        ('5', time(15, 20), time(16, 55)),
        ('6', time(17, 5), time(18, 40)),
    ],
}


def fill_default_period_template():
    """
    Заполняет таблицу PeriodTemplate значениями по умолчанию.
    """
    template_objects = [
        PeriodTemplate(
            day_of_week=day,
            lesson_number=lesson_number,
            start_time=start_time,
            end_time=end_time
        )
        for days, lessons in DEFAULT_PERIOD_TEMPLATE.items()
        for day in days
        for lesson_number, start_time, end_time in lessons
    ]

    with transaction.atomic():
        # Удаляем все существующие записи
        PeriodTemplate.objects.all().delete()
        PeriodTemplate.objects.bulk_create(template_objects)


def apply_template_changes(start_date_str):
    try:
        start_date = dateparser.parse(start_date_str, date_formats=['%Y-%m-%d', '%d.%m.%Y'])
    except ValueError:
        raise ValueError('Неверный формат даты')

    today = timezone.now().date()
    if start_date < today:
        raise ValueError('Шаблон не применяется к прошедшим датам')

    end_date = Period.objects.aggregate(max_date=Max('date'))['max_date']

    if end_date:
        with transaction.atomic():
            for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days + 1)):
                day_of_week = single_date.strftime('%A')
                templates = PeriodTemplate.objects.filter(day_of_week=day_of_week)
                for template in templates:
                    Period.objects.filter(date=single_date, lesson_number=template.lesson_number).update(
                        start_time=template.start_time,
                        end_time=template.end_time
                    )
    else:
        raise ValueError('В таблице Period не найдены записи для обновления.')
