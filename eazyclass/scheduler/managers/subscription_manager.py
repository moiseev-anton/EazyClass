import logging
from collections import defaultdict
from typing import Dict, Optional, Set

from django.apps import apps
from django.db.models import Prefetch
from polymorphic.managers import PolymorphicManager
from scheduler.models.social_account_model import PlatformValue

logger = logging.getLogger(__name__)


class SubscriptionManager(PolymorphicManager):
    def get_subscriber_chat_ids(
            self,
            obj_ids: Set[int],
            platform: PlatformValue,
    ) -> Dict[int, list[str]]:
        if not obj_ids:
            return {}

        # Определяем поле объекта подписки
        if not hasattr(self.model, "subscription_object_field"):
            raise AttributeError(f"{self.model.__name__} must define `subscription_object_field`")
        obj_id_field = f"{self.model.subscription_object_field}_id"

        SocialAccount = apps.get_model("scheduler", "SocialAccount")

        # Prefetch аккаунтов платформы
        account_prefetch = Prefetch(
            "user__accounts",
            queryset=SocialAccount.objects.filter(
                platform=platform,
                is_blocked=False,
                chat_id__isnull=False  # Только с chat_id
            ).only("chat_id"),
            to_attr="platform_accounts",
        )

        qs = (
            self.filter(
                **{f"{obj_id_field}__in": obj_ids},
                user__is_active=True,
                user__accounts__platform=platform,
                user__accounts__is_blocked=False,
                user__accounts__chat_id__isnull=False,
            )
            .select_related("user")
            .prefetch_related(account_prefetch)
        )

        mapping: Dict[int, list[str]] = defaultdict(list)
        for sub in qs:
            obj_id = getattr(sub, obj_id_field)
            accounts = getattr(sub.user, "platform_accounts", [])
            for acc in accounts:
                if acc.chat_id:
                    mapping[obj_id].append(acc.chat_id)

        return dict(mapping)
