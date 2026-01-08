from django.db import models
from scheduler.managers.mixins import IDMappableMixin


class TeacherManager(models.Manager, IDMappableMixin):
    ...

