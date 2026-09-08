from django.db import models

from scheduler.managers.mixins import IDMappableMixin


class LessonAnnotationManager(models.Manager, IDMappableMixin):
    ...
