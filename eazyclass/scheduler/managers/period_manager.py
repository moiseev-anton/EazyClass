import logging
from datetime import date
from typing import Iterable

from django.db import models
from scheduler.managers.mixins import IDMappableMixin

logger = logging.getLogger(__name__)


class PeriodManager(models.Manager, IDMappableMixin):
    def get_date_map(self, period_ids: Iterable[int]) -> dict[int, date]:
        return dict(self.filter(id__in=period_ids).values_list("id", "date"))