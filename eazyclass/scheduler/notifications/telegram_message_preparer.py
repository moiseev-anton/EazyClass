import logging
from collections import defaultdict
from itertools import chain
from typing import Any, Dict

from scheduler.dtos import NotificationItem
from scheduler.models import (
    Group,
    GroupSubscription,
    Period,
    Teacher,
    TeacherSubscription,
)
from scheduler.notifications.messages import format_lessons_updated_message

logger = logging.getLogger(__name__)


def prepare_notifications(cls, update_summary: Dict[str, Any]) -> list[NotificationItem]:
    """Подготовка списка уведомлений на основе сводки изменений."""
    lesson_items = chain.from_iterable(update_summary.values())

    period_ids = set()
    group_ids = set()
    teacher_ids = set()

    group_periods = defaultdict(set)
    teacher_periods = defaultdict(set)

    for lesson in lesson_items:
        pid = lesson["period_id"]
        period_ids.add(pid)

        if gid := lesson["group_id"]:
            group_ids.add(gid)
            group_periods[gid].add(pid)

        if tid := lesson["teacher_id"]:
            teacher_ids.add(tid)
            teacher_periods[tid].add(pid)

    # Получаем адресатов
    group_destination_chats = GroupSubscription.objects.get_telegram_chat_ids_map(group_ids)
    teacher_destination_chats = TeacherSubscription.objects.get_telegram_chat_ids_map(teacher_ids)

    # Названия
    group_names = dict(Group.objects.filter(id__in=group_ids).values_list("id", "title"))
    teacher_names = dict(Teacher.objects.filter(id__in=teacher_ids).values_list("id", "short_name"))

    # Карта period_id -> date
    period_dates = Period.objects.get_date_map(period_ids)

    messages = []

    for group_id, chats in group_destination_chats.items():
        if not chats:
            continue

        dates = [
            period_dates[p_id]
            for p_id in group_periods[group_id]
            if p_id in period_dates
        ]

        name = group_names.get(group_id, group_id)
        text = format_lessons_updated_message(name, dates)
        messages.append(NotificationItem(message=text, destinations=chats))

    for teacher_id, chats in teacher_destination_chats.items():
        if not chats:
            continue

        dates = [
            period_dates[p_id]
            for p_id in teacher_periods[teacher_id]
            if p_id in period_dates
        ]

        name = teacher_names.get(teacher_id, teacher_id)
        text = format_lessons_updated_message(name, dates)
        messages.append(NotificationItem(message=text, destinations=chats))

    return messages
