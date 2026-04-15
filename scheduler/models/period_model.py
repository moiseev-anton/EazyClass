from django.db import models

from scheduler.managers import PeriodManager
from scheduler.models.period_template_models import Timing


class Period(models.Model):
    lesson_number = models.PositiveIntegerField()
    date = models.DateField()
    start_time = models.TimeField(default=None, null=True, blank=True)
    end_time = models.TimeField(default=None, null=True, blank=True)
    part = models.PositiveSmallIntegerField(
        default=0,
        choices=[
            (0, "Полная пара"),
            (1, "1-я половина"),
            (2, "2-я половина"),
        ],
    )

    objects = PeriodManager()

    class Meta:
        unique_together = ("date", "lesson_number", "part")
        indexes = [
            models.Index(fields=["date", "lesson_number"]),
        ]
        verbose_name = 'Period'
        verbose_name_plural = 'Periods'

    def save(self, *args, **kwargs) -> None:
        self.pre_save_actions()
        super().save(*args, **kwargs)

    def pre_save_actions(self):
        """
        Дополняет объект Period значениями start_time и end_time из шаблона.
        Если шаблон отсутствует, start_time и end_time остаются None.
        """
        if not self.start_time or not self.end_time:

            timing = Timing.objects.get_for_period(
                date=self.date, lesson_number=self.lesson_number
            )
            if not timing:
                return

            start, end = timing.get_time_range(self.part)

            self.start_time = start
            self.end_time = end

    def __str__(self) -> str:
        start = self.start_time.strftime("%H:%M") if self.start_time else "—"
        end = self.end_time.strftime("%H:%M") if self.end_time else "—"
        part_str = f"({self.part})" if self.part else ""
        return f"{self.lesson_number}{part_str} | {self.date:%d.%m.%Y} | {start}–{end}"
