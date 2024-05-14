import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime
from datetime import timedelta

import requests
from bs4 import BeautifulSoup
from celery import group
from celery import shared_task
from django.core.cache import cache
from django.db import transaction
from django.db.models import Model, Max
from django.utils import timezone

from ..models import Group, Subject, Lesson, Classroom, Teacher

MAIN_URL = 'https://bincol.ru/rasp/'
TIMEOUT_LESSONS = 60 * 60 * 24 * 3
TIMEOUT_OTHER = 60 * 60 * 24 * 7
LESSON_CUTOFF_TIMEDELTA = timedelta(hours=1)

logger = logging.getLogger(__name__)


def generate_cache_key(model_name: str, params: dict) -> str:
    """
    Генерирует уникальный ключ кэша для заданной модели и параметров.

    Args:
        model_name (str): Название модели.
        params (dict): Словарь параметров, которые идентифицируют объект модели.

    Returns:
        str: Уникальный ключ кэша.
    """
    params_string = json.dumps(params, sort_keys=True)
    hash_digest = hashlib.md5(params_string.encode()).hexdigest()
    return f"{model_name}_{hash_digest}"


def cache_lesson_key(data: dict):
    """
    Кэширует ключ урока.

    Args:
        data (Dict): Данные урока для генерации ключа кэша.
    """
    key = generate_cache_key('Lesson', data)
    cache.set(key, 'exists', timeout=TIMEOUT_LESSONS)


def get_or_create_cached(model: Model, defaults: dict, timeout: int = TIMEOUT_OTHER):
    """
    Получает из кэша или создает объект модели в БД с кэшированием, используя словарь атрибутов.

    Args:
        model (Model): Класс модели Django, например, Teacher, Subject или Classroom.
        defaults (dict): Словарь с полями и значениями для поиска или создания объекта.
        timeout (int): Время жизни кэша в секундах.

    Returns:
        Model: Экземпляр найденного или созданного объекта.
    """
    key = generate_cache_key(model.__name__, defaults)
    obj = cache.get(key)
    if not obj:
        obj, created = model.objects.get_or_create(**defaults)
        cache.set(key, obj, timeout=timeout)  # Установка кэша с заданным тайм-аутом
    return obj


def get_soup_from_url(url: str) -> BeautifulSoup:
    """
    Получает содержимое веб-страницы по указанному URL и возвращает объект BeautifulSoup.

    Args:
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


# @shared_task
def parse_lessons_data(group_id: int) -> list[dict]:
    """
    Парсит данные уроков для конкретной группы и возвращает список уроков в виде словарей.

    Args:
        group (Group): Объект группы, для которой происходит парсинг уроков.

    Returns:
        list[dict]: Список словарей, каждый из которых содержит данные об уроке.
    """
    group_ = Group.objects.get(id=group_id)
    url = MAIN_URL + group_.link
    soup = get_soup_from_url(url)

    current_date = None
    lessons_data = []
    for row in soup.find_all('tr', class_='shadow'):
        if row.find(colspan=True):
            date_str = row.text.strip().split(' - ')[0]
            current_date = datetime.strptime(date_str, '%d.%m.%Y').date()
        elif current_date:
            cells = row.find_all('td')
            if len(cells) == 5:
                lesson_dict = {
                    'date': current_date,
                    'lesson_number': cells[0].text.strip(),
                    'subject_title': cells[1].text.strip(),
                    'classroom_title': cells[2].text.strip() or "(дист)",
                    'teacher_name': cells[3].text.strip(),
                    'subgroup': cells[4].text.strip(),
                    'group': group_
                }
                lessons_data.append(lesson_dict)
    return lessons_data


def fetch_all_lessons_data_async():
    group_ids = Group.objects.filter(is_active=True).values_list('id', flat=True)
    tasks = [parse_lessons_data.s(group_id) for group_id in group_ids]
    task_group = group(tasks)
    result = task_group.apply_async()
    lessons_data = result.get()  # Получение результатов выполнения всех задач
    return [item for sublist in lessons_data for item in sublist]


def classify_lessons(all_lessons_data: list[dict]) -> (list[Lesson], list[Lesson]):
    """
    Классифицирует уроки на основе данных из списка всех уроков, определяя, какие из них следует создать
    или обновить в базе данных.

    Args:
        all_lessons_data (list[dict]): Список словарей, содержащий данные уроков.

    Returns:
        (list[Lesson], list[Lesson]): Два списка объектов Lesson:
                                          первый для создания новых уроков, второй для обновления существующих.
    """
    current_time = timezone.now()
    lessons_to_create = []
    lessons_to_update = []
    affected_groups_dates = defaultdict(set)

    for data in all_lessons_data:
        teacher = get_or_create_cached(Teacher, {'full_name': data['teacher_name']}, TIMEOUT_OTHER)
        classroom = get_or_create_cached(Classroom, {'title': data['classroom_title']}, TIMEOUT_OTHER)
        subject = get_or_create_cached(Subject, {'title': data['subject_title']}, TIMEOUT_OTHER)

        lesson = Lesson(
            group=data['group'],
            date=data['date'],
            lesson_number=data['lesson_number'],
            teacher=teacher,
            classroom=classroom,
            subject=subject,
            is_active=True
        )
        key = generate_cache_key('Lesson', data)
        if cache.get(key):
            lesson.updated_at = current_time
            lessons_to_update.append(lesson)
        else:
            lessons_to_create.append(lesson)
            cache_lesson_key(data)  # Кэшируем ключ
            affected_groups_dates[lesson.group.id].add(lesson.date)  # Наполняем список для уведомлений

    return lessons_to_create, lessons_to_update, affected_groups_dates


def deactivate_canceled_lessons(model: Model, delta: timedelta):
    """
    Деактивирует записи, которые не обновлялись в течение заданного временного интервала и
    имеют при этом дату проведения не раньше сегодняшней. Это предназначено для отмененных или измененных
    занятий, которые не актуальны на момент проведения.

    Args:
    model (Model): Класс модели Django, который нужно обновить.
    delta (timedelta): Временной интервал, после которого записи считаются устаревшими.
    """
    latest_update = model.objects.aggregate(latest=Max('updated_at'))['latest']
    cutoff_time = latest_update - delta
    today = timezone.now().date()

    # Получаем QuerySet занятий, которые будут деактивированы
    lessons_to_deactivate = model.objects.filter(
        updated_at__lt=cutoff_time,
        date__gte=today,
        is_active=True
    )

    # Собираем идентификаторы затронутых групп и даты
    affected_groups_dates = defaultdict(set)
    for lesson in lessons_to_deactivate:
        affected_groups_dates[lesson.group.id].add(lesson.date)

    # Производим деактивацию
    lessons_to_deactivate.update(is_active=False)

    return affected_groups_dates


# @shared_task
def update_all_lessons():
    """
    Задача, выполняемая Celery. Извлекает данные всех уроков, классифицирует их для обновления
    или создания в базе данных, и выполняет соответствующие массовые операции.

    Выполняет также деактивацию отмененых занятий.
    """
    with transaction.atomic():
        # Получаем данные о всех занятиях
        all_lessons_data = fetch_all_lessons_data_async()

        # Сепарируем старые данные от новых, отбираем данные для рассылки уведомлений
        lessons_to_create, lessons_to_update, affected_groups = classify_lessons(all_lessons_data)

        Lesson.objects.bulk_create(lessons_to_create)
        Lesson.objects.bulk_update(lessons_to_update, ['updated_at'])

        affected_groups_deactivated = deactivate_canceled_lessons(Lesson, LESSON_CUTOFF_TIMEDELTA)
        affected_groups.update(affected_groups_deactivated)
        # notify_users(affected_groups)












