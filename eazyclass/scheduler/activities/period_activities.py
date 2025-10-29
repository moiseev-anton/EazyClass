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
