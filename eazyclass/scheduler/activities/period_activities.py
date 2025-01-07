from datetime import time
# from datetime import timedelta
import logging

# import dateparser
from django.db import transaction
# from django.utils import timezone

from scheduler.models import PeriodTemplate, Timing, TimingWeekDay

logger = logging.getLogger(__name__)


class DefaultPeriodTemplateFiller:
    DEFAULT_PERIOD_TEMPLATES = {
        1: {(time(8, 0), time(9, 35)): (0, 1, 2, 3, 4, 5)},
        2: {(time(9, 45), time(11, 20)): (0, 1, 2, 3, 4, 5)},
        3: {
            (time(12, 20), time(13, 55)): (0, 1, 2, 3, 4),
            (time(11, 50), time(13, 25)): (5,),
        },
        4: {
            (time(14, 5), time(15, 40)): (0, 1, 2, 3, 4),
            (time(13, 35), time(15, 10)): (5,),
        },
        5: {
            (time(15, 50), time(17, 25)): (0, 1, 2, 3, 4),
            (time(15, 20), time(16, 55)): (5,),
        },
        6: {
            (time(17, 35), time(19, 10)): (0, 1, 2, 3, 4),
            (time(17, 5), time(18, 40)): (5,),
        },
    }

    def __init__(self):
        self.templates = self.DEFAULT_PERIOD_TEMPLATES
        self.period_template_map = {}
        self.timing_map = {}

    @transaction.atomic
    def fill(self):
        self.clear_existing_data()
        self.create_period_templates()
        self.create_timings()
        self.create_timing_weekdays()

    @staticmethod
    def clear_existing_data():
        """
        Удаляет все существующие записи в связанных таблицах.
        """
        TimingWeekDay.objects.all().delete()
        Timing.objects.all().delete()
        PeriodTemplate.objects.all().delete()

    def create_period_templates(self):
        """
        Создает записи PeriodTemplate и сохраняет их в мапу.
        """
        period_templates = [
            PeriodTemplate(lesson_number=lesson_number)
            for lesson_number in self.templates.keys()
        ]
        PeriodTemplate.objects.bulk_create(period_templates)
        self.period_template_map = {
            template.lesson_number: template.id
            for template in PeriodTemplate.objects.all()
        }

    def create_timings(self):
        """
        Создает записи Timing и сохраняет их в мапу.
        """
        timings = []
        for lesson_number, timing_data in self.templates.items():
            for (start_time, end_time), weekdays in timing_data.items():
                timings.append(
                    Timing(
                        period_template_id=self.period_template_map[lesson_number],
                        start_time=start_time,
                        end_time=end_time,
                    )
                )
        Timing.objects.bulk_create(timings)
        self.timing_map = {
            (timing.period_template_id, timing.start_time, timing.end_time): timing.id
            for timing in Timing.objects.all()
        }

    def create_timing_weekdays(self):
        """
        Создает записи TimingWeekDay.
        """
        timing_weekdays = []
        for lesson_number, timing_data in self.templates.items():
            for (start_time, end_time), weekdays in timing_data.items():
                timing_id = self.timing_map[
                    (self.period_template_map[lesson_number], start_time, end_time)
                ]
                for day in weekdays:
                    timing_weekdays.append(
                        TimingWeekDay(
                            timing_id=timing_id,
                            day_of_week=day,
                        )
                    )
        TimingWeekDay.objects.bulk_create(timing_weekdays)


def fill_default_period_template():
    filler = DefaultPeriodTemplateFiller()
    filler.fill()

# def apply_template_changes(start_date_str):
#     start_date = dateparser.parse(start_date_str, date_formats=['%Y-%m-%d', '%d.%m.%Y']).date()
#     today = timezone.now().date()
#
#     if start_date < today:
#         raise ValueError('Шаблон не применяется к прошедшим датам')
#
#     end_date = Period.objects.get_max_date()
#
#     if not end_date:
#         raise ValueError('В таблице Period не найдены записи для обновления.')
#
#     existing_periods = Period.objects.filter(date__gte=start_date, date__lte=end_date)
#
#     if end_date:
#         with transaction.atomic():
#             for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days + 1)):
#                 day_of_week = single_date.weekday()
#                 templates = PeriodTemplate.objects.filter(day_of_week=day_of_week)
#                 for template in templates:
#                     Period.objects.filter(date=single_date, lesson_number=template.lesson_number).update(
#                         start_time=template.start_time,
#                         end_time=template.end_time
#                     )
#     else:
#         raise ValueError('В таблице Period не найдены записи для обновления.')
#
#
# class TemplateUpdater:
#     def __init__(self, start_date_str, end_date_str=None):
#         """
#         Инициализация с датами начала и конца обновления.
#         """
#         self.today = timezone.now().date()
#         self.start_date = dateparser.parse(start_date_str, date_formats=['%Y-%m-%d', '%d.%m.%Y'])
#         self.end_date = dateparser.parse(end_date_str, date_formats=['%Y-%m-%d', '%d.%m.%Y']) if end_date_str else None
#         self.max_date = Period.objects.get_max_date()
#
#         if not self.start_date:
#             raise ValueError('Некорректный формат даты')
#
#         if self.start_date < self.today:
#             raise ValueError('Шаблон не применяется к прошедшим датам')
#
#         self.template_map = PeriodTemplate.objects.get_template_dict()
#
#     def _get_periods_to_update(self):
#         """
#         Получает все записи для обновления, основываясь на start_date и end_date.
#         """
#         filter_params = {'date__gte': self.start_date}
#         if self.end_date:
#             filter_params['date__lte'] = self.end_date
#
#         return Period.objects.filter(**filter_params)
#
#     def _compare_and_collect_updates(self, periods):
#         """
#         Сравнивает существующие записи с шаблонами и собирает те, которые нужно обновить.
#         """
#         periods_to_update = []
#
#         for period in periods:
#             template = self.template_map.get((period.date.strftime('%A'), period.lesson_number))
#             if not template:
#                 continue  # Если шаблон для дня недели и урока отсутствует
#
#             # Проверяем необходимость обновления
#             if period.start_time != template.start_time or period.end_time != template.end_time:
#                 period.start_time = template.start_time
#                 period.end_time = template.end_time
#                 periods_to_update.append(period)
#
#         return periods_to_update
#
#     def apply_changes(self):
#         """
#         Основной метод, применяющий изменения шаблона к таблице Period.
#         """
#         existing_periods = self._get_periods_to_update()
#         periods_to_update = self._compare_and_collect_updates(existing_periods)
#
#         # Массовое обновление
#         if periods_to_update:
#             Period.objects.bulk_update(periods_to_update, ['start_time', 'end_time'])
#             logger.info(f"Обновлено {len(periods_to_update)} записей в таблице Period.")
#         else:
#             logger.info("Нет записей для обновления.")
