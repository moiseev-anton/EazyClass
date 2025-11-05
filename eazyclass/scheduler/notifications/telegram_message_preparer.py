import logging
from itertools import chain
from typing import Any, Dict, Iterable, Set

from django.db.models import Model, Prefetch, QuerySet

from scheduler.dtos import NotificationItem
from scheduler.models import (
    GroupSubscription,
    Platform,
    SocialAccount,
    TeacherSubscription,
)

logger = logging.getLogger(__name__)


class TelegramMessagePreparer:
    @classmethod
    def prepare_notifications(cls, update_summary: Dict[str, Any]) -> list[NotificationItem]:
        """Подготовка списка уведомлений на основе сводки изменений."""
        all_items = chain.from_iterable(update_summary.values())
        fields_map = cls._extract_fields_sets(all_items, ("group_id", "teacher_id"))

        group_ids = fields_map.get("group_id", set())
        teacher_ids = fields_map.get("teacher_id", set())

        logger.debug(
            f"Изменения затронули группы: {group_ids}, преподавателей: {teacher_ids}"
        )

        groups_map = cls._collect_notifications(
            subscription_model=GroupSubscription,
            obj_field="group",
            obj_ids=group_ids,
            name_attr="title",
            message_text_template="Расписание для группы {name} изменено",
        )
        teachers_map = cls._collect_notifications(
            subscription_model=TeacherSubscription,
            obj_field="teacher",
            obj_ids=teacher_ids,
            name_attr="short_name",
            message_text_template="Расписание для преподавателя {name} изменено",
        )

        return list(chain.from_iterable(m.values() for m in (groups_map, teachers_map) if m))

    @staticmethod
    def _extract_fields_sets(items: Iterable[Dict], fields: Iterable[str]) -> Dict[str, Set]:
        """Извлекает уникальные значения указанных полей из списка словарей."""
        result = {field: set() for field in fields}
        for item in items:
            for field in fields:
                if (value := item.get(field)) is not None:
                    result[field].add(value)
        return result

    @classmethod
    def _collect_notifications(
        cls,
        subscription_model: type[Model],
        obj_field: str,
        obj_ids: Set[int],
        name_attr: str,
        message_text_template: str,
    ) -> dict[int, NotificationItem]:
        """Общая логика получения подписчиков и формирования уведомлений."""
        entity_map = {}
        if not obj_ids:
            return entity_map

        subs_qs: QuerySet = cls._build_query(subscription_model, obj_field, obj_ids)

        for sub in subs_qs:
            user = sub.user
            if not user.is_active:
                continue

            telegram_accounts = getattr(user, "telegram_accounts", [])
            if not telegram_accounts:
                continue

            obj = getattr(sub, obj_field)
            if obj.id not in entity_map:
                obj_name = getattr(obj, name_attr)
                entity_map[obj.id] = NotificationItem(
                    message=message_text_template.format(name=obj_name), destinations=[]
                )

            chat_id = telegram_accounts[0].chat_id
            entity_map[obj.id].destinations.append(chat_id)

        logger.debug(f"Получено {len(subs_qs)} подписок для {subscription_model.__name__}")
        return entity_map

    @staticmethod
    def _build_query(sub_model: type[Model], obj_field: str, obj_ids: Set[int]) -> QuerySet:
        """Сборка QS для подписок."""
        telegram_prefetch = Prefetch(
            "user__accounts",
            queryset=SocialAccount.objects.filter(
                platform=Platform.TELEGRAM, is_blocked=False
            ).only("chat_id"),
            to_attr="telegram_accounts",
        )

        filter_kwargs = {
            f"{obj_field}_id__in": obj_ids,
            "user__is_active": True,
        }

        return (
            sub_model.objects.filter(**filter_kwargs)
            .select_related("user", obj_field)
            .prefetch_related(telegram_prefetch)
        )
