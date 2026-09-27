from django.db import transaction
from django.utils import timezone

from scheduler.fetched_data_sync.utils import fetch_page_content
from scheduler.fetched_data_sync.faculties.parser import parse_faculties_page
from scheduler.fetched_data_sync.dto import FacultyData
from scheduler.models import Faculty, Group

def refresh_faculties_and_groups(base_url: str, endpoint: str):
    """Главная функция обновления факультетов и групп."""
    html = fetch_page_content(f"{base_url}{endpoint}")
    faculties: list[FacultyData] = parse_faculties_page(html)

    # Если не получили ни одного факультета значит со страницей что-то не так, не выполняем обновление.
    # Код ответа 200 не гарантирует корректность страницы.
    # TODO: Рассмотреть возможность проверки валидности страницы по наличию конкретных тегов
    if not faculties:
        raise RuntimeError("Факультеты не найдены — обновление отменено")

    faculty_ids = set()
    group_ids = set()

    with transaction.atomic():
        for fac_data in faculties:
            faculty, created = Faculty.objects.get_or_create(
                title=fac_data.title,
                defaults={
                    "short_title": fac_data.short_title,
                },
            )
            faculty_ids.add(faculty.id)

            if not created and not faculty.is_active:
                faculty.is_active = True
                faculty.save(update_fields=["is_active"])

            for group_data in fac_data.groups:
                group, _ = Group.objects.update_or_create(
                    endpoint=group_data.endpoint,
                    defaults={
                        "title": group_data.title,
                        "grade": group_data.course,
                        "faculty": faculty,
                        "is_active": True,
                        "updated_at": timezone.now(),
                    },
                )
                group_ids.add(group.id)

        # Деактивируем отсутствующие
        f_count = Faculty.objects.filter(is_active=True).exclude(id__in=faculty_ids).update(is_active=False)
        g_count = Group.objects.filter(is_active=True).exclude(id__in=group_ids).update(is_active=False)

    # Return only after the transaction committed; the task owns the final log.
    return {"faculties_count": len(faculty_ids), "groups_count": len(group_ids),
            "deactivated_faculties_count": f_count, "deactivated_groups_count": g_count}
