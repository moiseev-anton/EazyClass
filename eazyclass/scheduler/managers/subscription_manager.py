import logging

from django.apps import apps
from django.db.models import Prefetch
from polymorphic.managers import PolymorphicManager
from scheduler.models.social_account_model import Platform

logger = logging.getLogger(__name__)


class SubscriptionManager(PolymorphicManager):
    def get_telegram_chat_ids_map(self, obj_ids):
        if not obj_ids:
            return {}

            # Определяем поле объекта подписки
        if not hasattr(self.model, "subscription_object_field"):
            raise AttributeError(f"{self.model.__name__} must define `subscription_object_field`")
        obj_id_field = f"{self.model.subscription_object_field}_id"

        SocialAccount = apps.get_model("scheduler", "SocialAccount")

        # Предзагрузка Telegram-аккаунтов
        telegram_prefetch = Prefetch(
            "user__accounts",
            queryset=SocialAccount.objects.filter(
                platform=Platform.TELEGRAM, is_blocked=False
            ).only("chat_id"),
            to_attr="telegram_accounts",
        )

        qs = (
            self.get_queryset()
            .filter(**{f"{obj_id_field}__in": obj_ids}, user__is_active=True)
            .select_related("user")
            .prefetch_related(telegram_prefetch)
        )

        mapping: dict[int, list[int]] = {}
        for sub in qs:
            obj_id = getattr(sub, obj_id_field)
            mapping.setdefault(obj_id, [])

            accounts = getattr(sub.user, "telegram_accounts", [])
            for acc in accounts:
                mapping[obj_id].append(acc.chat_id)

        return mapping
