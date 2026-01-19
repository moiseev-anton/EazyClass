import logging
from typing import Iterable

from django.db import models

logger = logging.getLogger(__name__)


class SocialAccountManager(models.Manager):
    def mark_chats_blocked(self, platform: str, chat_ids: Iterable[int | str]) -> int:
        return self.filter(platform=platform, chat_id__in=set(chat_ids)).update(is_blocked=True)

    def get_staff_chat_ids(self, platform: str) -> list[int | str]:
        return list(
            self.filter(platform=platform, user__is_staff=True)
            .only("chat_id")
            .values_list("chat_id", flat=True)
        )
