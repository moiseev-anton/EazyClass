from django.db import models

from scheduler.managers import PeriodManager
from scheduler.models.period_template_models import PeriodTemplate


class Period(models.Model):
    lesson_number = models.PositiveIntegerField()
    date = models.DateField()
    start_time = models.TimeField(default=None, null=True, blank=True)
    end_time = models.TimeField(default=None, null=True, blank=True)

    objects = PeriodManager()

    class Meta:
        unique_together = ("date", "lesson_number")
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
            template = PeriodTemplate.objects.get_template_for_day(
                date=self.date, lesson_number=self.lesson_number
            )
            if template and template.timings.exists():
                timing = template.timings.first()
                self.start_time = timing.start_time
                self.end_time = timing.end_time

    def __str__(self) -> str:
        start = self.start_time.strftime("%H:%M") if self.start_time else "—"
        end = self.end_time.strftime("%H:%M") if self.end_time else "—"
        return f"{self.lesson_number} | {self.date:%d.%m.%Y} | {start}–{end}"
