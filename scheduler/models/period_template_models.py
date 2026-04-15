from datetime import date as DateClass, date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.db import models

from scheduler.managers import PeriodTemplateManager, TimingManager


class PeriodTemplate(models.Model):
    lesson_number = models.PositiveIntegerField()
    start_date = models.DateField(default=DateClass.today)
    end_date = models.DateField(null=True, blank=True, default=None)

    objects = PeriodTemplateManager()

    class Meta:
        db_table = "scheduler_period_template"
        ordering = ['start_date']
        unique_together = ('lesson_number', 'start_date')
        verbose_name = 'Period Template'
        verbose_name_plural = 'Period Templates'

    def __str__(self):
        return f"Урок {self.lesson_number} с {self.start_date} по {self.end_date}"


class Timing(models.Model):
    period_template = models.ForeignKey(PeriodTemplate, related_name='timings', on_delete=models.CASCADE)
    start_time = models.TimeField()
    end_time = models.TimeField()
    part_duration = models.PositiveSmallIntegerField(
        default=45, help_text="Продолжительность одной полупары в минутах (>= 1)"
    )

    objects = TimingManager()

    class Meta:
        constraints = [
            # Уже существующая проверка
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="check_timing_start_before_end",
            ),
        ]

    def clean(self):
        """Валидация на уровне Python (вызывается в формах, админке, full_clean)"""
        super().clean()

        if self.part_duration == 0:
            return

        # переводим время в минуты
        start = datetime.combine(date.min, self.start_time)
        end = datetime.combine(date.min, self.end_time)

        duration_minutes = int((end - start).total_seconds() // 60)

        if self.part_duration * 2 > duration_minutes:
            raise ValidationError(
                {
                    "part_duration": (
                        "Удвоенная длительность полупары превышает длительность пары"
                    )
                }
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def get_time_range(self, part: int) -> tuple[time | None, time | None]:
        """
        Возвращает временной диапазон в зависимости от part.

        part:
            0 — полная пара
            1 — первая половина
            2 — вторая половина
        """
        # разделение запрещено
        if self.part_duration == 0:
            return None, None

        # full
        if part == 0:
            return self.start_time, self.end_time

        start_dt = datetime.combine(date.min, self.start_time)
        end_dt = datetime.combine(date.min, self.end_time)
        half = timedelta(minutes=self.part_duration)

        if part == 1:
            return self.start_time, (start_dt + half).time()

        if part == 2:
            return (end_dt - half).time(), self.end_time

        # кривые данные
        return None, None


class TimingWeekDay(models.Model):
    """
    Модель для связывания шаблона расписания с днями недели.
    """
    timing = models.ForeignKey(Timing, related_name='weekdays', on_delete=models.CASCADE)
    day_of_week = models.SmallIntegerField()  # 0 для понедельника, 1 для вторника и т.д.

    class Meta:
        unique_together = ('timing', 'day_of_week')
