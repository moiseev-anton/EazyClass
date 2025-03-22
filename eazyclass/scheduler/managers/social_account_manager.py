import logging

from django.db import models

logger = logging.getLogger(__name__)


class SocialAccountManager(models.Manager):
    ...

