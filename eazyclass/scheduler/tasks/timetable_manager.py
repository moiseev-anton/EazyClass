import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from scheduler.models import Period, PeriodTemplate

logger = logging.getLogger(__name__)


class PeriodFiller:
    DEFAULT_DAYS_AHEAD = 28

    def __init__(self):
        self.today = timezone.now().date()
        self.template_map = PeriodTemplate.objects.get_template_dict()
        self.start_date = self._calculate_start_date()
        self.end_date = None
        self.new_periods = []

    def _calculate_start_date(self):
        """
        Определяет начальную дату заполнения расписания.
        """
        max_date = Period.objects.get_max_date()
        return (max_date + timedelta(days=1)) if max_date else self.today

    def set_end_date(self, days_ahead=DEFAULT_DAYS_AHEAD):
        """
        Устанавливает конечную дату заполнения расписания.
        Проверяет, что конечная дата не меньше начальной.
        """
        calculated_end_date = self.today + timedelta(days=days_ahead)
        if calculated_end_date < self.start_date:
            raise ValueError(f"Таблица уже заполнена на {(self.start_date - self.today).days} дней вперёд.")
        self.end_date = calculated_end_date

    def collect_new_periods(self):
        """
        Формирует список новых записей для таблицы Period на основе шаблонов.
        """
        # Итератор диапазона дат
        date_range = (self.start_date + timedelta(days=n) for n in range((self.end_date - self.start_date).days + 1))

        # Создаем объекты для массовой вставки
        for single_date in date_range:
            day_of_week = single_date.weekday()
            day_templates = self.template_map.get(day_of_week, [])
            for template in day_templates:
                self.new_periods.append(
                    Period(
                        date=single_date,
                        lesson_number=template["lesson_number"],
                        start_time=template["start_time"],
                        end_time=template["end_time"],
                    )
                )

    def fill_periods_by_template(self, days_ahead=DEFAULT_DAYS_AHEAD):
        """
        Основной метод, выполняющий заполнение расписания на основе шаблона.
        """
        self.set_end_date(days_ahead)
        self.collect_new_periods()

        if self.new_periods:
            created = Period.objects.bulk_create(self.new_periods)
            logger.info(f"Добавлено {len(created)} записей в таблицу Period.")
        else:
            logger.info("Нет новых записей для добавления.")

    @classmethod
    def fill(cls, days_ahead=DEFAULT_DAYS_AHEAD):
        """
        Удобный метод для запуска заполнения через Celery или вручную.
        """
        filler = cls()
        filler.fill_periods_by_template(days_ahead=days_ahead)


@shared_task(queue='periodic_tasks')
def fill_periods_task(days_ahead=28):
    PeriodFiller.fill(days_ahead=days_ahead)
