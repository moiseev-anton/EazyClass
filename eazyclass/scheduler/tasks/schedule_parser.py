import asyncio
import logging
import re
from datetime import datetime
from typing import List, Dict, Any

import bs4
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction

from .db_queries import synchronize_lessons
from ..models import Group, Subject, Lesson, LessonBuffer, Classroom, Teacher, LessonTime

MAIN_URL = 'https://bincol.ru/rasp/'
CACHE_TIMEOUT = 60 * 60 * 24 * 7
logger = logging.getLogger(__name__)


class ScheduleParser:
    lesson_number_pattern = re.compile(r'^[1-9]$')
    date_pattern = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')

    def __init__(self, groups: List[Dict], session: ClientSession):
        self.groups = groups  # Список словарей с id и link групп
        self.session = session  # Сессия aiohttp
        self.lessons = []  # Список объектов Lesson
        self.fetch_failed_ids = set()  # ID групп, для которых не удалось получить данные
        self.parse_failed_ids = set()  # ID групп, для которых не удалось распарсить данные
        self.success_ids = set()  # ID групп, для которых всё прошло успешно
        self.unique_teachers = set()
        self.unique_classrooms = set()
        self.unique_subjects = set()
        self.unique_lesson_times = set()

    async def fetch_group_data(self, group_id, link):
        try:
            url = f"{MAIN_URL}{link}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logging.warning(f"Failed to fetch data for group {group_id}: {response.status}")
                    self.fetch_failed_ids.add(group_id)
        except Exception as e:
            logging.error(f"Error fetching data for group {group_id}: {e}")
            self.fetch_failed_ids.add(group_id)

    def extract_lessons_data(self, group_id, html):
        try:
            soup = BeautifulSoup(html, 'lxml')
            # Парсинг данных и добавление их в self.lessons
            lessons_data = []
            current_date = None

            # Проходим по всем строкам таблицы (tr тегам)
            for row in soup.find_all('tr', class_='shadow'):
                # Получаем ячейки строки (td теги)
                cells = row.find_all('td')
                if len(cells) == 1:
                    current_date = self.parse_date_cell(cells[0])
                elif len(cells) == 5 and current_date:
                    lesson_dict = self.parse_lesson_cells(cells)
                    lesson_dict.update({'date': current_date, 'group': group_id})
                    lessons_data.append(lesson_dict)
                else:
                    raise ValueError(f"Некорректная структура таблицы для группы {group_id}")

            logger.debug(f"Выполнен парсинг для группы c ID {group_id}: получено {len(lessons_data)} уроков.")
            self.success_ids.add(group_id)
            return lessons_data
        except Exception as e:
            logger.error(f"Ошибка при парсинге группы {group_id}: {e}")
            self.parse_failed_ids.add(group_id)

    @staticmethod
    def parse_date_cell(cell: bs4.Tag) -> datetime.date:
        date_str = cell.text.strip().split(' - ')[0]
        return datetime.strptime(date_str, '%d.%m.%Y').date()

    @staticmethod
    def parse_lesson_cells(cells: list):
        lesson_number = cells[0].text.strip()
        # Проверяем что номер урока 1-9
        if not ScheduleParser.lesson_number_pattern.match(lesson_number):
            raise ValueError(f"Некорректный номер урока '{lesson_number}'")
        return {
            'lesson_number': int(lesson_number),
            'subject_title': cells[1].text.strip() or 'не указано',
            'classroom_title': cells[2].text.strip() or '(дист)',
            'teacher_name': cells[3].text.strip() or 'не указано',
            'subgroup': cells[4].text.strip() or '0'
        }

    async def process_group(self, group):
        html = await self.fetch_group_data(group['id'], group['link'])
        if html:
            lessons_data = self.extract_lessons_data(group['id'], html)
            self.lessons.extend(lessons_data)

    def collect_unique_elements(self, lesson_dict: dict):
        self.unique_teachers.add(lesson_dict['teacher_name'])
        self.unique_classrooms.add(lesson_dict['classroom_title'])
        self.unique_subjects.add(lesson_dict['subject_title'])
        self.unique_lesson_times.add((lesson_dict['date'], lesson_dict['lesson_number']))

    def prepare_unique_sets(self):
        for lesson in self.lessons:
            self.collect_unique_elements(lesson)

    async def run(self):
        async with ClientSession() as session:
            self.session = session
            tasks = [self.process_group(group) for group in self.groups]
            await asyncio.gather(*tasks)

    def get_or_create_related_objects(self):
        existing_teachers = Teacher.objects.filter(full_name__in=self.unique_teachers)
        teacher_map = {teacher.full_name: teacher.id for teacher in existing_teachers}

        existing_classrooms = Classroom.objects.filter(title__in=self.unique_classrooms)
        classroom_map = {classroom.title: classroom.id for classroom in existing_classrooms}

        existing_subjects = Subject.objects.filter(title__in=self.unique_subjects)
        subject_map = {subject.title: subject.id for subject in existing_subjects}

        existing_lesson_times = LessonTime.objects.filter(
            date__in={date for date, _ in self.unique_lesson_times},
            lesson_number__in={lesson_number for _, lesson_number in self.unique_lesson_times}
        )
        lesson_time_map = {
            (lesson_time.date, lesson_time.lesson_number): lesson_time.id
            for lesson_time in existing_lesson_times
        }


async def main():
    groups = Group.objects.groups_links()
    async with ClientSession() as session:
        parser = ScheduleParser(groups, session)
        await parser.run()
        # parser.save_to_db()


def build_lesson_obj_from_data(data: dict, timeout=CACHE_TIMEOUT) -> Lesson:
    teacher_id = get_or_create_cached_id(Teacher, {'full_name': data['teacher_name']}, timeout)
    classroom_id = get_or_create_cached_id(Classroom, {'title': data['classroom_title']}, timeout)
    subject_id = get_or_create_cached_id(Subject, {'title': data['subject_title']}, timeout)
    lesson_time_id = get_or_create_cached_id(
        LessonTime, {'date': data['date'], 'lesson_number': data['lesson_number']}, timeout
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
    lesson_number_pattern = re.compile(r'^[1-9]$')
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
        lesson_obj = build_lesson_obj_from_data(lesson_data)
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


async def fetch_group_data(session: aiohttp.ClientSession, group_id: int, link: str) -> Dict[str, Any]:
    url = f"{MAIN_URL}{link}"
    response_text = await fetch_response_from_url(session, url)

    if not response_text:
        return {'group_id': group_id, 'error': 'fetch_failed'}

    try:
        soup = BeautifulSoup(response_text, 'lxml')
        lessons_data = extract_lessons_data(group_id, soup)
        return {'group_id': group_id, 'lessons_data': lessons_data}
    except Exception as e:
        logger.error(f"Ошибка при парсинге данных для группы {group_id}: {e}")
        return {'group_id': group_id, 'error': 'parse_failed'}


# Асинхронная функция для сбора данных для всех групп с ограничением на количество одновременных запросов
async def gather_group_data(groups: List[Dict[str, Any]], max_concurrent_requests: int = 10) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(max_concurrent_requests)  # Ограничиваем количество одновременных запросов

    async def bounded_fetch(session, group):
        async with semaphore:
            return await fetch_group_data(session, group['id'], group['link'])

    async with aiohttp.ClientSession() as session:
        tasks = [bounded_fetch(session, group) for group in groups]
        return await asyncio.gather(*tasks)


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def update_schedule(self):
    try:
        groups = Group.objects.groups_links()

        loop = asyncio.get_event_loop()
        results = loop.run_until_complete(gather_group_data(groups))

        process_data_final.delay(results)

        logger.info(f"Обновление расписания завершено.")
    except Exception as e:
        logger.error(f"Ошибка обновления расписания: {e}")
        raise self.retry(exc=e)
