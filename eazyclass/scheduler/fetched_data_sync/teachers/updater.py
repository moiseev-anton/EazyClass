import logging
from collections import defaultdict

from scheduler.fetched_data_sync.teachers.parser import parse_teachers_page
from scheduler.fetched_data_sync.utils import fetch_page_content, normalize_person_name
from scheduler.models import Teacher

logger = logging.getLogger(__name__)


def refresh_teachers_endpoints(base_url: str, page_path: str):
    """Главная функция обновления факультетов и групп."""
    html = fetch_page_content(f"{base_url}{page_path}")
    teachers_map = parse_teachers_page(html, page_path)
    db_teachers = Teacher.objects.filter(is_active=True)

    teacher_lookup = build_teacher_lookup(db_teachers)

    updated_count = 0

    for name, endpoint in teachers_map.items():
        normalized_name = normalize_person_name(name)
        if teacher := teacher_lookup.get(normalized_name):
            if teacher.endpoint is None or teacher.endpoint != endpoint:
                teacher.endpoint = endpoint
                teacher.save(update_fields=["endpoint"])
                updated_count += 1

    logger.info(f"Обновлено {updated_count} записей преподавателей")


def build_teacher_lookup(
    teachers: list[Teacher],
) -> dict[str, Teacher]:
    """
    Возвращает:
    - словарь нормализованное_имя → Teacher
    """
    buckets: dict[str, list[Teacher]] = defaultdict(list)

    for teacher in teachers:
        norm_name = normalize_person_name(teacher.short_name)
        buckets[norm_name].append(teacher)

    lookup: dict[str, Teacher] = {}

    for norm_name, items in buckets.items():
        if len(items) == 1:
            lookup[norm_name] = items[0]
        else:
            logger.warning(
                "Обнаружена коллизия имен Teacher (%s): %s",
                norm_name,
                ", ".join(f"[ID:{t.id} {t.short_name}]" for t in items),
            )

    return lookup

