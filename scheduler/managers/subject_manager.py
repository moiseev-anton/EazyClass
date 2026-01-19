from django.db import models
from scheduler.managers.mixins import IDMappableMixin


class SubjectManager(models.Manager, IDMappableMixin):
    ...
