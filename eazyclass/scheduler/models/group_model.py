from django.db import models

from scheduler.managers import GroupManager
from scheduler.models.abstract_models import TimestampedModel


class Group(TimestampedModel):
    title = models.CharField(max_length=255)
    faculty = models.ForeignKey(
        "scheduler.Faculty", related_name="groups", on_delete=models.CASCADE, null=True
    )
    endpoint = models.CharField(max_length=128) # эндпоинт страницы расписания
    grade = models.PositiveSmallIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    # + created_at из TimestampedModel
    # + updated_at из TimestampedModel

    objects = GroupManager()

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["faculty", "is_active"]),
            models.Index(fields=["grade", "is_active"]),
            models.Index(fields=["title"]),
        ]

    def __str__(self):
        return f"{self.title}"

    def get_display_name(self):
        return self.title
