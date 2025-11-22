import logging

from scheduler.fetched_data_sync.teachers.parser import parse_teachers_page
from scheduler.fetched_data_sync.utils import fetch_page_content
from scheduler.models import Teacher

logger = logging.getLogger(__name__)


def refresh_teachers_endpoints(base_url: str, page_path: str):
    """Главная функция обновления факультетов и групп."""
    html = fetch_page_content(f"{base_url}{page_path}")
    teachers_map = parse_teachers_page(html, page_path)
    teachers = Teacher.objects.filter(is_active=True)

    updated_count = 0
    for teacher in teachers:
        endpoint = teachers_map.get(teacher.short_name)
        if endpoint and (teacher.endpoint is None or teacher.endpoint != endpoint):
            teacher.endpoint = endpoint
            teacher.save(update_fields=["endpoint"])
            updated_count += 1

    logger.info(f"Обновлено {updated_count} записей преподавателей")

