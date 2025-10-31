import logging
from typing import Iterable

from django.db import models

logger = logging.getLogger(__name__)


class SocialAccountManager(models.Manager):
    def mark_chats_blocked(self, platform: str, chat_ids: Iterable[int | str]) -> int:
        return self.filter(platform=platform, chat_id__in=chat_ids).update(is_blocked=True)
