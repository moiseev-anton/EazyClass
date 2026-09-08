from django.core.exceptions import ValidationError
from django.db import models


class AudienceMode(models.TextChoices):
    ALL_USERS = "all_users", "Все активные пользователи"
    SUBSCRIBED_USERS = "subscribed_users", "Все с подписками"
    GROUP_SUBSCRIBERS = "group_subscribers", "Подписчики групп"
    TEACHER_SUBSCRIBERS = "teacher_subscribers", "Подписчики преподавателей"


class ChannelMode(models.TextChoices):
    ALL_AVAILABLE = "all_available", "Все доступные каналы"
    SELECTED = "selected", "Выбранные каналы"


def validate_audience(value):
    """Validate the versioned filter structure; database references are checked separately."""
    if not isinstance(value, dict):
        raise ValidationError("Аудитория должна быть объектом.")
    allowed = {"version", "mode", "faculty_ids", "grades", "group_ids"}
    if set(value) - allowed:
        raise ValidationError("Неизвестные поля аудитории.")
    if type(value.get("version")) is not int or value["version"] != 1:
        raise ValidationError("Поддерживается версия аудитории 1.")
    if value.get("mode") not in AudienceMode.values:
        raise ValidationError("Неизвестный режим аудитории.")
    for key in ("faculty_ids", "grades", "group_ids"):
        items = value.get(key, [])
        if not isinstance(items, list) or any(type(item) is not int or item <= 0 for item in items):
            raise ValidationError(f"{key}: ожидается список положительных целых чисел.")
        if len(items) != len(set(items)):
            raise ValidationError(f"{key}: значения не должны повторяться.")
        if items and value["mode"] != AudienceMode.GROUP_SUBSCRIBERS:
            raise ValidationError("Фильтры групп доступны только для подписчиков групп.")
    if any(grade > 32767 for grade in value.get("grades", [])):
        raise ValidationError("Значение курса выходит за допустимый диапазон.")


def validate_platforms(value):
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise ValidationError("Каналы должны быть списком непустых строк.")
    if len(value) != len(set(value)):
        raise ValidationError("Каналы не должны повторяться.")


def default_audience():
    return {"version": 1, "mode": AudienceMode.ALL_USERS.value}
