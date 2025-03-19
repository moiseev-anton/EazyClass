from django.db import models

from scheduler.managers import SubjectManager


class Subject(models.Model):
    title = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    objects = SubjectManager()

    class Meta:
        indexes = [
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return f"{self.title}"
