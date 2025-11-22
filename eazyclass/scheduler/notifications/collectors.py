import logging
from collections import defaultdict
from itertools import chain
from typing import Any, Dict, Iterable, List, Set

from scheduler.dtos import NotificationItem
from scheduler.models import (
    Group,
    GroupSubscription,
    Lesson,
    Period,
    Teacher,
    TeacherSubscription,
)
from scheduler.models.social_account_model import PlatformValue
from scheduler.notifications.messages import (
    format_refresh_lessons_message,
    format_start_lesson_message_for_group,
    format_start_lesson_message_for_teacher,
)

logger = logging.getLogger(__name__)


def collect_refresh_notifications(
    refresh_summary: Dict[str, Any], platform: PlatformValue
) -> list[NotificationItem]:
    """Подготовка списка уведомлений на основе сводки изменений."""
    lesson_items = chain.from_iterable(refresh_summary.values())

    if not lesson_items:
        return []

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
    group_chats = GroupSubscription.objects.get_subscriber_chat_ids(group_ids, platform)
    logger.debug(f"group_chats: {group_chats}")
    teacher_chats = TeacherSubscription.objects.get_subscriber_chat_ids(teacher_ids, platform)
    logger.debug(f"teacher_chats: {teacher_chats}")

    # Названия
    group_names = dict(Group.objects.filter(id__in=group_chats.keys()).values_list("id", "title"))
    logger.debug(f"group_names: {group_names}")
    teacher_names = dict(Teacher.objects.filter(id__in=teacher_chats.keys()).values_list("id", "short_name"))
    logger.debug(f"teacher_names: {teacher_names}")

    # Словарь period_id -> date
    period_dates = Period.objects.get_date_map(period_ids)

    notifications = []

    # Сборка уведомлений для групп
    for group_id, chats in group_chats.items():
        if not chats:
            continue
        dates = [period_dates[p_id] for p_id in group_periods[group_id] if p_id in period_dates]
        name = group_names.get(group_id, group_id)
        message = format_refresh_lessons_message(name, dates)
        notifications.append(NotificationItem(message=message, destinations=chats))

    for teacher_id, chats in teacher_chats.items():
        if not chats:
            continue
        dates = [period_dates[p_id] for p_id in teacher_periods[teacher_id] if p_id in period_dates]
        name = teacher_names.get(teacher_id, teacher_id)
        message = format_refresh_lessons_message(name, dates)
        notifications.append(NotificationItem(message=message, destinations=chats))

    return notifications


def collect_group_start(
    lessons: Iterable[Lesson], platform: PlatformValue
) -> List[NotificationItem]:
    """Внутренняя: групповые уведомления о старте."""
    if not lessons:
        return []

    # Собираем уникальные ID студенческих групп
    group_ids: Set[int] = {lesson.group_id for lesson in lessons if lesson.group_id}

    if not group_ids:
        return []

    # Чаты подписчиков для каждой студенческой группы
    group_chats: Dict[int, list[str]] = GroupSubscription.objects.get_subscriber_chat_ids(
        group_ids, platform=platform
    )

    # Группировка уроков по студенческим группам
    #  (у одной группы может быть больше одного урока одновременно).
    lessons_by_group = defaultdict(list)
    for lesson in lessons:
        if lesson.group:
            lessons_by_group[lesson.group].append(lesson)

    notifications = []
    for group, group_lessons in lessons_by_group.items():
        chats = group_chats.get(group.id)
        if not chats:
            continue

        message = format_start_lesson_message_for_group(group_lessons)
        notifications.append(NotificationItem(message=message, destinations=chats))
        logger.debug(f"Собрано {len(chats)} чатов для группы {group.title}")

    return notifications


def collect_teacher_start(
    lessons: Iterable[Lesson], platform: PlatformValue
) -> List[NotificationItem]:
    """Внутренняя: учительские уведомления о старте."""
    if not lessons:
        return []

    # Собираем уникальные ID учителей
    teacher_ids: Set[int] = {lesson.teacher_id for lesson in lessons if lesson.teacher_id}
    if not teacher_ids:
        return []

    # Чаты
    teacher_chats: Dict[int, list[str]] = TeacherSubscription.objects.get_subscriber_chat_ids(
        teacher_ids, platform=platform
    )

    notifications = []
    for lesson in lessons:
        teacher = lesson.teacher
        if not teacher:
            continue

        chats = teacher_chats.get(teacher.id)
        if not chats:
            continue

        message = format_start_lesson_message_for_teacher(lesson)
        notifications.append(NotificationItem(message=message, destinations=chats))
        logger.debug(f"Собрано {len(chats)} чатов для преподавателя {teacher.short_name}")

    return notifications
