import logging

from django.db import models
from scheduler.managers.mixins import IDMappableMixin

logger = logging.getLogger(__name__)


class TeacherManager(models.Manager, IDMappableMixin):
    ...

