from django.db import models

from scheduler.managers import ClassroomManager


class Classroom(models.Model):
    title = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)

    objects = ClassroomManager()

    class Meta:
        indexes = [
            models.Index(fields=['title']),
        ]

        verbose_name = 'Classroom'
        verbose_name_plural = 'Classrooms'

    def __str__(self):
        return f"{self.title}"
