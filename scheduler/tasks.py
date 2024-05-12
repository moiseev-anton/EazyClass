import logging
from datetime import datetime
from datetime import timedelta


import requests
from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction
from django.db.models import Model, Max
from django.utils import timezone
from django.core.cache import cache

from .models import Faculty, Group, Subject, Lesson, Classroom, Teacher

MAIN_URL = 'https://bincol.ru/rasp/'
GROUPS_PAGE_LINK = 'grupp.php'

logger = logging.getLogger(__name__)


from django.core.cache import cache
from django.db.models import Model
import hashlib
import json

def get_or_create_cached(model: Model, defaults: dict, timeout=86400):
    """
    Получает из кэша или создает объект модели в БД с кэшированием, используя словарь атрибутов.

    Args:
        model (Model): Класс модели Django, например, Teacher, Subject или Classroom.
        defaults (dict): Словарь с полями и значениями для поиска или создания объекта.
        timeout (int): Время жизни кэша в секундах.

    Returns:
        Model instance: Экземпляр найденного или созданного объекта.
    """
    # Создаем уникальный ключ кэша на основе имени модели и значений атрибутов
    serialized_data = json.dumps(defaults, sort_keys=True)
    hash_key = hashlib.md5(serialized_data.encode()).hexdigest()
    cache_key = f"{model.__name__.lower()}_{hash_key}"

    obj = cache.get(cache_key)
    if not obj:
        obj, created = model.objects.get_or_create(**defaults)
        cache.set(cache_key, obj, timeout=timeout)  # Установка кэша с заданным тайм-аутом
    return obj

def get_soup_from_url(url: str) -> BeautifulSoup:
    """
    Получает содержимое веб-страницы по указанному URL и возвращает объект BeautifulSoup.

    Parameters:
    url (str): URL-адрес веб-страницы.

    Returns:
    BeautifulSoup: Объект BeautifulSoup, представляющий содержимое веб-страницы.

    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return BeautifulSoup(response.content, 'lxml')
    except requests.RequestException as e:
        logger.error(f"Ошибка при запросе к {url}: {str(e)}")
        return BeautifulSoup()


def deactivate_old_records(model: Model, delta: timedelta):
    """
    Деактивирует записи, которые не обновлялись в течение заданного временного интервала.

    Args:
    model (Model): Класс модели Django, который нужно обновить.
    delta (timedelta): Временной интервал, после которого записи считаются устаревшими.
    """
    latest_update = model.objects.aggregate(latest=Max('updated_at'))['latest']
    threshold_date = latest_update - delta
    model.objects.filter(updated_at__lt=threshold_date, is_active=True).update(is_active=False)


def parse_group_list():
    url = MAIN_URL + GROUPS_PAGE_LINK
    soup = get_soup_from_url(url)
    faculty_blocks = soup.find_all('p', class_='shadow')

    for block in faculty_blocks:
        faculty_name = block.text.strip().split(' ', 1)[1]
        faculty, created = Faculty.objects.get_or_create(title=faculty_name)
        logger.debug(f"Faculty {'created' if created else 'updated'}: {faculty.title}")

        groups = block.find_next_sibling('p').find_all('a')
        for group in groups:
            group_name = group.text
            group_url = group['href']
            group_grade = group_name[0] if group_name else ''
            Group.objects.update_or_create(
                title=group_name,
                faculty=faculty,
                defaults={
                    'link': group_url,
                    'grade': group_grade,
                }
            )
            logger.debug(f"Group {'created' if created else 'updated'}: {group.title}")
        faculty.calculate_short_title()


@shared_task
def update_groups():
    with transaction.atomic():
        parse_group_list()
        deactivate_old_records(Faculty, timedelta(days=1))  # потом попробудем брать timedelta из celery-beat
        deactivate_old_records(Group, timedelta(days=1))


# Парсинг занятий
def deactivate_not_actual_lessons(model: Model, delta: timedelta):
    """
    Деактивирует записи, которые не обновлялись в течение заданного временного интервала и
    имеют дату меньше сегодняшней.

    Args:
    model (Model): Класс модели Django, который нужно обновить.
    delta (timedelta): Временной интервал, после которого записи считаются устаревшими.
    """
    latest_update = model.objects.aggregate(latest=Max('updated_at'))['latest']
    threshold_date = latest_update - delta
    today = timezone.now().date()
    print(today)

    model.objects.filter(
        updated_at__lt=threshold_date,
        date__gte=today,
        is_active=True
    ).update(is_active=False)


def parse_lessons(group):
    url = MAIN_URL + group.link
    soup = get_soup_from_url(url)

    current_date = None
    for row in soup.find_all('tr', class_='shadow'):
        if row.find(colspan=True):  # Это строка с датой
            date_str = row.text.strip().split(' - ')[0]
            current_date = datetime.strptime(date_str, '%d.%m.%Y').date()

        else:
            cells = row.find_all('td')
            if len(cells) == 5:
                lesson_number = cells[0].text.strip()
                subject_title = cells[1].text.strip()
                classroom_title = cells[2].text.strip() or "Дист."
                teacher_name = cells[3].text.strip()
                subgroup = cells[4].text.strip()  # or '0'

                teacher = get_or_create_cached(Teacher, {'full_name':teacher_name})
                classroom = get_or_create_cached(Classroom, {'title': classroom_title})
                subject = get_or_create_cached(Subject, {'title': subject_title})

                Lesson.objects.update_or_create(
                    group=group,
                    date=current_date,
                    lesson_number=lesson_number,
                    subject=subject,
                    defaults={
                        'classroom': classroom,
                        'teacher': teacher,
                        'subgroup': subgroup,
                        'is_active': True,
                    }
                )


@shared_task
def update_all_lessons():
    with transaction.atomic():
        active_groups = Group.objects.filter(is_active=True)
        for group in active_groups:
            parse_lessons(group)
        deactivate_not_actual_lessons(Lesson, timedelta(hours=5))


# def notify_users(group, change):
#     # Отправка уведомлений пользователям, подписанным на группу
#     # Форматирование сообщения в зависимости от типа изменения
#     message = format_schedule_changes(change)
#     send_notification(group.subscribers, message)
#
#
# def format_schedule_changes(changes):
#     message = "Изменение в расписании:\n"
#     for date, lessons in changes.items():
#         message += f"{date.strftime('%d.%m.%Y')} - {date.strftime('%A')}\n"
#         for lesson in lessons:
#             classroom_info = lesson.classroom.title if lesson.classroom.title else "Дист"
#             message += f"{lesson.lesson_number} {lesson.subject.title} {classroom_info} {lesson.teacher.full_name}\n"
#         message += "\n"  # Добавить пустую строку между днями
#     return message