import hashlib
import json
import logging
import re
from datetime import datetime
import asyncio

import requests
from bs4 import BeautifulSoup
from celery import shared_task, chord, group, chain
from django.core.cache import cache
from django.db import transaction
from django.db.models import Model

from .db_queries import synchronize_lessons, fetch_all_subscribers
from ..models import Group, Subject, Lesson, LessonBuffer, Classroom, Teacher, LessonTime
from eazyclass.telegrambot.bot import bot

MAIN_URL = 'https://bincol.ru/rasp/'
CACHE_TIMEOUT = 60 * 60 * 24 * 7
logger = logging.getLogger(__name__)


def fetch_response_from_url(url: str) -> requests.Response:
    """Отправляет HTTP-запрос GET к указанному URL и возвращает ответ."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        logger.error(f"Ошибка получения ответа от {url}: {e}")
        raise


def generate_cache_key(model_class: Model, params: dict) -> str:
    """Генерирует уникальный ключ кэша для заданной модели и параметров."""
    if params.get('date'):
        params['date'] = params['date'].isoformat()
    params_string = json.dumps(params, sort_keys=True)
    key = model_class.__name__ + params_string
    hash_digest = hashlib.md5(key.encode()).hexdigest()
    return hash_digest


def get_or_create_cached_id(model_class: Model, lookup: dict, timeout: int = CACHE_TIMEOUT) -> int:
    """
    Получает объект из кэша или базы данных, создает объект при необходимости.
    """
    cache_key = generate_cache_key(model_class, lookup)
    obj_id = cache.get(cache_key)
    if obj_id:
        # logger.debug(f"Для {model_class.__name__} с параметрами {lookup} получен ID {obj_id} из кэша.")
        return obj_id

    obj, created = model_class.objects.get_or_create(**lookup)
    cache.set(cache_key, obj.id, timeout=timeout)
    # logger.debug(f"Для {model_class.__name__} с параметрами {lookup} получен ID {obj.id} из БД и кэширован.")
    return obj.id


def get_lesson_obj_from_data(data: dict, timeout=CACHE_TIMEOUT) -> Lesson:
    date = datetime.strptime(data['date'], '%d.%m.%Y').date()
    teacher_id = get_or_create_cached_id(Teacher, {'full_name': data['teacher_name']}, timeout)
    classroom_id = get_or_create_cached_id(Classroom, {'title': data['classroom_title']}, timeout)
    subject_id = get_or_create_cached_id(Subject, {'title': data['subject_title']}, timeout)
    lesson_time_id = get_or_create_cached_id(
        LessonTime, {'date': date, 'lesson_number': data['lesson_number']}, timeout
    )

    lesson = Lesson(
        group_id=data['group_id'],
        subgroup=data['subgroup'],
        lesson_time_id=lesson_time_id,
        teacher_id=teacher_id,
        classroom_id=classroom_id,
        subject_id=subject_id
    )

    return lesson


def extract_lessons_data(group_id: int, soup: BeautifulSoup):
    """Парсит данные расписания из объекта BeautifulSoup для определённой группы."""
    lessons_data = []
    current_date = None
    lesson_number_pattern = re.compile(r'^[1-6]$')
    date_pattern = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')

    for row in soup.find_all('tr', class_='shadow'):
        if 'colspan' in str(row):
            current_date = None
            date_str = row.text.strip().split(' - ')[0]
            if date_pattern.match(date_str):
                current_date = date_str
            else:
                logger.warning(f"Получен неверный формат даты '{date_str}'")
                raise ValueError

        elif current_date and row.find('td'):
            cells = row.find_all('td')
            if len(cells) == 5:
                lesson_number = cells[0].text.strip()
                # проверяем что номер урока 1-6
                if lesson_number_pattern.match(lesson_number):
                    lessons_data.append({
                        'date': current_date,
                        'lesson_number': lesson_number,
                        'subject_title': cells[1].text.strip() or 'не указано',
                        'classroom_title': cells[2].text.strip() or '(дист)',
                        'teacher_name': cells[3].text.strip() or 'не указано',
                        'subgroup': cells[4].text.strip() or '0',
                        'group_id': group_id
                    })
                else:
                    logger.warning(f"Некорректный номер урока '{lesson_number}' {current_date} для группы {group_id}.")

    logger.debug(f"Выполнен парсинг для группы c ID {group_id}: получено {len(lessons_data)} уроков.")
    return lessons_data


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def parse_group_data(self, group_id, link):
    url = f"{MAIN_URL}{link}"
    try:
        response = fetch_response_from_url(url)
        soup = BeautifulSoup(response.content, 'lxml')
        lessons_data = extract_lessons_data(group_id, soup)
        return {'group_id': group_id, 'lessons_data': lessons_data}
    except Exception as e:
        if self.request.retries == self.max_retries:
            logger.error(f"Не удалось получить данные для группы ID={group_id}: {str(e)}")
            return {'group_id': group_id, 'lessons_data': None, 'error': 'final_failure'}
        raise self.retry(exc=e)


def update_database(groups_ids: set, lessons_data: list[Lesson]):
    new_lessons = []
    for lesson_data in lessons_data:
        lesson_obj = get_lesson_obj_from_data(lesson_data)
        if lesson_obj:
            new_lessons.append(lesson_obj)

    try:
        with transaction.atomic():
            LessonBuffer.objects.bulk_create(new_lessons)
            affected_entities = synchronize_lessons(groups_ids)
            LessonBuffer.objects.all().delete()

        logger.info(f"Данные обновлены для {len(groups_ids)} групп")
        return affected_entities

    except Exception as e:
        logger.error(f"Ошибка при обновлении данных в БД {groups_ids}: {str(e)}")
        raise


@shared_task(queue='periodic_tasks')
def process_data_final(results):
    # Обработка собранных данных
    lessons_data = []
    successful_group_ids = set()
    failed_group_ids = set()
    for result in results:
        if result.get('error') == 'final_failure':
            failed_group_ids.add(result['group_id'])
        else:
            lessons_data.extend(result['lessons_data'])
            successful_group_ids.add(result['group_id'])
    affected_entities = update_database(successful_group_ids, lessons_data)
    return affected_entities
    # if failed_group_ids:
    #     pass
    # Уведомляем администратора об ошибках (добавить потом)
    # notify_admins_of_failures(failed_updates)
    # Обрабатываем успешные результаты


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def update_schedule(self):
    try:
        fetch_response_from_url(MAIN_URL)
        logger.info('Сайт доступен. Начинается обновление расписания.')

        groups = cache.get('all_groups_ids_and_links')
        if not groups:
            groups = Group.objects.filter(is_active=True).values('id', 'link')
            cache.set('all_groups_ids_and_links', list(groups), timeout=CACHE_TIMEOUT)

        tasks = [parse_group_data.s(group_['id'], group_['link']) for group_ in groups]
        callback = process_data_final.s()
        notification_task = send_notifications.s()

        workflow = chain(chord(tasks)(callback), notification_task.s())
        workflow.apply_async()
        logger.info(f"Обновление расписания завершено.")
    except Exception as e:
        logger.error(f"Ошибка обновления расписания: {e}")
        raise self.retry(exc=e)


@shared_task(queue='periodic_tasks')
def send_notifications(affected_entities_map: dict):
    logger.debug(f"Начата отправка уведомлений")
    subscribers_map = fetch_all_subscribers(affected_entities_map)
    notification_type_tasks = []
    for entity_type, entity_map in subscribers_map.items():
        if entity_map:  # Убедимся, что есть подписчики перед созданием задачи
            entity_info_map = affected_entities_map[entity_type]
            notification_type_tasks.append(send_notifications_for_entity.s(entity_type, entity_map, entity_info_map))

    task_group = group(notification_type_tasks)
    task_group.apply_async()
    logger.debug("Задачи по отправке уведомлений запланированы")


@shared_task(queue='periodic_tasks')
def send_notifications_for_entity(entity_map: dict, entity_info_map: dict):
    tasks = []
    for entity_id, subscribers_set in entity_map.items():
        dates = ", ".join(sorted(entity_info_map[entity_id]))
        message = f"Ваше расписание на {dates} изменено. Ознакомтесь с новым расписанием."
        tasks.append(send_notifications_for_subscribers(message, subscribers_set))
    task_group = group(tasks)
    task_group.apply_async()
    logger.debug("Задачи по отправке уведомлений для группы подписчиков выполнены")


@shared_task
def send_notifications_for_subscribers(message: str, telegram_ids: set):
    asyncio.run(async_send_notifications(message, telegram_ids))


async def async_send_notifications(message, telegram_ids):
    for telegram_id in telegram_ids:
        try:
            await bot.send_message(telegram_id, message)
            logger.debug(f"Уведомление успешно отправлено пользователю {telegram_id}")
        except Exception as e:
            logger.error(f"Ошибка при отправке уведомления пользователю {telegram_id}: {e}")

