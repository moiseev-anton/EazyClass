import logging

from django.db import models

logger = logging.getLogger(__name__)


class GroupManager(models.Manager):
    def link_map(self):
        return list(self.filter(is_active=True).values_list('id', 'link'))
