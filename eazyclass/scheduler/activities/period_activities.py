from datetime import time
from datetime import timedelta

import dateparser
from django.db import transaction
from django.utils import timezone

from scheduler.models import Period, PeriodTemplate

DEFAULT_PERIOD_TEMPLATE = {
    (0, 1, 2, 3, 4,): [
        ('1', time(8, 0), time(9, 35)),
        ('2', time(9, 45), time(11, 20)),
        ('3', time(12, 20), time(13, 55)),
        ('4', time(14, 5), time(15, 40)),
        ('5', time(15, 50), time(17, 25)),
        ('6', time(17, 35), time(19, 10)),
    ],
    (5,): [
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
    start_date = dateparser.parse(start_date_str, date_formats=['%Y-%m-%d', '%d.%m.%Y']).date()
    today = timezone.now().date()

    if start_date < today:
        raise ValueError('Шаблон не применяется к прошедшим датам')

    end_date = Period.objects.get_max_date()

    if not end_date:
        raise ValueError('В таблице Period не найдены записи для обновления.')

    existing_periods = Period.objects.filter(date__gte=start_date, date__lte=end_date)

    if end_date:
        with transaction.atomic():
            for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days + 1)):
                day_of_week = single_date.weekday()
                templates = PeriodTemplate.objects.filter(day_of_week=day_of_week)
                for template in templates:
                    Period.objects.filter(date=single_date, lesson_number=template.lesson_number).update(
                        start_time=template.start_time,
                        end_time=template.end_time
                    )
    else:
        raise ValueError('В таблице Period не найдены записи для обновления.')


class TemplateUpdater:
    def __init__(self, start_date_str, end_date_str=None):
        """
        Инициализация с датами начала и конца обновления.
        """
        self.today = timezone.now().date()
        self.start_date = dateparser.parse(start_date_str, date_formats=['%Y-%m-%d', '%d.%m.%Y'])
        self.end_date = dateparser.parse(end_date_str, date_formats=['%Y-%m-%d', '%d.%m.%Y']) if end_date_str else None
        self.max_date = Period.objects.get_max_date()

        if not self.start_date:
            raise ValueError('Некорректный формат даты')

        if self.start_date < self.today:
            raise ValueError('Шаблон не применяется к прошедшим датам')

        self.template_map = PeriodTemplate.objects.get_template_dict()


    def _get_periods_to_update(self):
        """
        Получает все записи для обновления, основываясь на start_date и end_date.
        """
        filter_params = {'date__gte': self.start_date}
        if self.end_date:
            filter_params['date__lte'] = self.end_date

        return Period.objects.filter(**filter_params)

    def _compare_and_collect_updates(self, periods):
        """
        Сравнивает существующие записи с шаблонами и собирает те, которые нужно обновить.
        """
        periods_to_update = []

        for period in periods:
            template = self.template_map.get((period.date.strftime('%A'), period.lesson_number))
            if not template:
                continue  # Если шаблон для дня недели и урока отсутствует

            # Проверяем необходимость обновления
            if period.start_time != template.start_time or period.end_time != template.end_time:
                period.start_time = template.start_time
                period.end_time = template.end_time
                periods_to_update.append(period)

        return periods_to_update

    def apply_changes(self):
        """
        Основной метод, применяющий изменения шаблона к таблице Period.
        """
        existing_periods = self._get_periods_to_update()
        periods_to_update = self._compare_and_collect_updates(existing_periods)

        # Массовое обновление
        if periods_to_update:
            Period.objects.bulk_update(periods_to_update, ['start_time', 'end_time'])
            logger.info(f"Обновлено {len(periods_to_update)} записей в таблице Period.")
        else:
            logger.info("Нет записей для обновления.")