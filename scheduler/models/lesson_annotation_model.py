from django.db import models

from scheduler.managers import LessonAnnotationManager


class LessonAnnotation(models.Model):
    title = models.CharField(max_length=255, unique=True)

    objects = LessonAnnotationManager()

    class Meta:
        verbose_name = 'Lesson annotation'
        verbose_name_plural = 'Lesson annotations'

    def __str__(self):
        return self.title
