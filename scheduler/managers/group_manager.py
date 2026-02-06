import logging

from django.db import models
from django.db.models import CharField
from django.db.models.functions import Cast

logger = logging.getLogger(__name__)


class GroupManager(models.Manager):
    def get_endpoint_map(self):
        return list(
            self.filter(is_active=True)
                .annotate(id_str=Cast('id', output_field=CharField()))
                .values_list('id_str', 'endpoint')
        )
