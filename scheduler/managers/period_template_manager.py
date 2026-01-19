import logging
from datetime import date as DateClass
from typing import Optional

from django.db import models
from django.db.models import Q

logger = logging.getLogger(__name__)


class PeriodTemplateManager(models.Manager):
    def get_template_for_day(self, date: DateClass | str, lesson_number: int) -> Optional['PeriodTemplate']:
        """
        Возвращает подходящий шаблон для номера урока и дня недели (по дате).
        """
        if isinstance(date, str):
            date = DateClass.fromisoformat(date)

        day_of_week_number = date.weekday()  # 0 - понедельник, 6 - воскресенье

        # Ищем подходящий PeriodTemplate с учетом даты и номера урока
        return self.filter(
            lesson_number=lesson_number,
            start_date__lte=date,
        ).filter(
            models.Q(end_date__gte=date) | models.Q(end_date__isnull=True)  # Дата окончания больше или NULL
        ).filter(
            timings__weekdays__day_of_week=day_of_week_number  # Связь через Timing и TimingWeekDay
        ).distinct().first()

    def overlapping(self, lesson_number: int, start_date: DateClass, end_date: Optional[DateClass],
                    exclude_pk: Optional[int] = None):
        """
        Возвращает пересекающиеся шаблоны с заданным периодом действия.

        Период считается пересекающимся, если:
        - Номер урока совпадает.
        - Начало периода не позже конца другого периода.
        - Конец периода не раньше начала другого периода или конец другого периода не указан.
        """
        query = Q(lesson_number=lesson_number) & (
                Q(start_date__lte=end_date if end_date else start_date) &
                (Q(end_date__gte=start_date) | Q(end_date__isnull=True))
        )

        if exclude_pk:
            query &= ~Q(pk=exclude_pk)

        return self.filter(query)
