from typing import Any

from django.db import models

from scheduler.models.abstract_models import TimestampedModel


class Lesson(TimestampedModel):
    group = models.ForeignKey('scheduler.Group', related_name='lessons', on_delete=models.CASCADE, null=True)
    period = models.ForeignKey('scheduler.Period', related_name='lessons', on_delete=models.CASCADE, null=True)
    subject = models.ForeignKey('scheduler.Subject', related_name='lessons', on_delete=models.CASCADE, null=True)
    teacher = models.ForeignKey('scheduler.Teacher', related_name='lessons', on_delete=models.CASCADE, null=True, blank=True)
    classroom = models.ForeignKey('scheduler.Classroom', related_name='lessons', on_delete=models.CASCADE, null=True)
    subgroup = models.CharField(max_length=1, default='0')
    is_active = models.BooleanField(default=True)
    # + updated_at из TimestampedModel
    # + created_at из TimestampedModel

    def __str__(self):
        return f"{self.group.title}({self.subgroup})-{self.period}-{self.subject}"

    class Meta:
        indexes = [
            models.Index(fields=['period', 'group']),
            models.Index(fields=['group', 'period', 'subgroup']),
        ]
        verbose_name = 'Lesson'
        verbose_name_plural = 'Lessons'

    def to_dict(self) -> dict[str, Any]:
        """Сериализация урока для JSON/Redis без лишних запросов."""
        return {
            "id": self.id,
            "group_id": self.group_id,
            "period_id": self.period_id,
            "subject_id": self.subject_id,
            "teacher_id": self.teacher_id,
            "classroom_id": self.classroom_id,
            "subgroup": self.subgroup,
        }
