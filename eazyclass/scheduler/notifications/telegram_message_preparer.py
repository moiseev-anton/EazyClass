import logging
from collections import defaultdict
from itertools import chain
from typing import Any, Dict, Iterable, Set

from django.db.models import Model, Prefetch, QuerySet

from scheduler.models import (
    GroupSubscription,
    Platform,
    SocialAccount,
    TeacherSubscription,
)

logger = logging.getLogger(__name__)


class TelegramMessagePreparer:
    @classmethod
    def prepare_notifications(cls, update_summary: Dict[str, Any]) -> list:
        """Подготовка списка уведомлений на основе сводки изменений."""
        try:
            fields_map = cls._extract_fields_sets(
                chain.from_iterable(update_summary.values()),
                ("group_id", "teacher_id"),
            )

            group_ids = fields_map.get("group_id", set())
            teacher_ids = fields_map.get("teacher_id", set())

            logger.info(
                f"Изменения затронули группы: {group_ids}, преподавателей: {teacher_ids}"
            )

            groups_map = cls._collect_notifications(
                GroupSubscription,
                "group",
                group_ids,
                "Расписание для группы {name} изменено",
                "title",
            )
            teachers_map = cls._collect_notifications(
                TeacherSubscription,
                "teacher",
                teacher_ids,
                "Расписание для преподавателя {name} изменено",
                "short_name",
            )

            return list(
                chain.from_iterable(
                    m.values() for m in (groups_map, teachers_map) if m
                )
            )

        except Exception as e:
            logger.error(f"Ошибка при формировании уведомлений")
            raise

    @staticmethod
    def _extract_fields_sets(
        items: Iterable[Dict], fields: Iterable[str]
    ) -> Dict[str, Set]:
        """Извлекает уникальные значения указанных полей из списка словарей."""
        result = {field: set() for field in fields}
        for item in items:
            for field in fields:
                if field in item:
                    result[field].add(item[field])
        return result

    @classmethod
    def _collect_notifications(
        cls,
        subscription_model: Model,
        obj_field: str,
        obj_ids: Set[int],
        message_template: str,
        name_attr: str,
    ) -> dict:
        """Общая логика получения подписчиков и формирования уведомлений."""
        entity_map = defaultdict(lambda: {"message": "", "destinations": []})
        if not obj_ids:
            return dict(entity_map)

        subs_qs: QuerySet = cls._build_query(subscription_model, obj_field, obj_ids)

        for sub in subs_qs:
            user = sub.user
            if not user.is_active:
                continue

            telegram_accounts = getattr(user, "telegram_accounts", [])
            if not telegram_accounts:
                continue

            telegram_chat_id = telegram_accounts[0].chat_id
            obj = getattr(sub, obj_field)
            obj_name = getattr(obj, name_attr)
            data = entity_map[obj.id]
            data["message"] = message_template.format(name=obj_name)
            data["destinations"].append(telegram_chat_id)

        logger.info(
            f"Получено {len(subs_qs)} подписок для {subscription_model.__name__}"
        )
        return dict(entity_map)

    @staticmethod
    def _build_query(sub_model: Model, obj_field: str, obj_ids: Set[int]) -> QuerySet:
        """Сборка QS для подписок."""
        telegram_prefetch = Prefetch(
            "user__accounts",
            queryset=SocialAccount.objects.filter(
                platform=Platform.TELEGRAM, is_blocked=False
            ).only("chat_id"),
            to_attr="telegram_accounts",
        )

        filter_kwargs = {
            f"{obj_field}_id__in": list(obj_ids),
            "user__is_active": True,
        }

        return (
            sub_model.objects.filter(**filter_kwargs)
            .select_related("user", obj_field)
            .prefetch_related(telegram_prefetch)
        )
