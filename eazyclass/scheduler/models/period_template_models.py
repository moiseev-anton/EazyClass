from datetime import date as DateClass

from django.db import models

from scheduler.managers import PeriodTemplateManager


class PeriodTemplate(models.Model):
    lesson_number = models.PositiveIntegerField()
    start_date = models.DateField(default=DateClass.today)
    end_date = models.DateField(null=True, blank=True, default=None)

    objects = PeriodTemplateManager()

    class Meta:
        db_table = "scheduler_period_template"
        ordering = ['start_date']
        unique_together = ('lesson_number', 'start_date')

    def __str__(self):
        return f"Урок {self.lesson_number} с {self.start_date} по {self.end_date}"


class Timing(models.Model):
    period_template = models.ForeignKey(PeriodTemplate, related_name='timings', on_delete=models.CASCADE)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='check_timing_start_before_end',
            ),
        ]


class TimingWeekDay(models.Model):
    """
    Модель для связывания шаблона расписания с днями недели.
    """
    timing = models.ForeignKey(Timing, related_name='weekdays', on_delete=models.CASCADE)
    day_of_week = models.SmallIntegerField()  # 0 для понедельника, 1 для вторника и т.д.

    class Meta:
        unique_together = ('timing', 'day_of_week')
