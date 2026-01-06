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
        verbose_name = 'Subject'
        verbose_name_plural = 'Subjects'

    def __str__(self):
        return f"{self.title}"
