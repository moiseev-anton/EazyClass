import asyncio
import logging
import random
import re
from datetime import datetime
from typing import List, Dict, Optional

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
        self.unique_data = {
            "teachers": set(),
            "classrooms": set(),
            "subjects": set(),
            "lesson_times": set(),
        }

    async def fetch_group_data(self, group_id, link):
        try:
            url = f"{MAIN_URL}{link}"
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.text()
                else:
                    logging.warning(f"Ошибка получения html со страницы {url}: {response.status}")
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
            'teacher_fullname': cells[3].text.strip() or 'не указано',
            'subgroup': cells[4].text.strip() or '0'
        }

    async def process_group(self, group):
        await asyncio.sleep(random.uniform(0.5, 2))
        html = await self.fetch_group_data(group['id'], group['link'])
        if html:
            lessons_data = self.extract_lessons_data(group['id'], html)
            self.lessons.extend(lessons_data)

    def collect_unique_elements(self):
        for lesson_dict in self.lessons:
            self.unique_data['teachers'].add(lesson_dict['teacher_fullname'])
            self.unique_data['classrooms'].add(lesson_dict['classroom_title'])
            self.unique_data['subjects'].add(lesson_dict['subject_title'])
            self.unique_data['lesson_times'].add((lesson_dict['date'], lesson_dict['lesson_number']))

    def related_objects_mapping(self):
        self.unique_data['teachers'] = Teacher.objects.get_or_create_map(self.unique_data['teachers'])
        self.unique_data['classrooms'] = Subject.objects.get_or_create_map(self.unique_data['classrooms'])
        self.unique_data['subjects'] = Classroom.objects.get_or_create_map(self.unique_data['subjects'])
        self.unique_data['lesson_times'] = LessonTime.objects.get_or_create_map(self.unique_data['lesson_times'])

    def build_lesson_objects(self):
        lesson_objects = []
        for lesson_dict in self.lessons:
            lesson_obj = Lesson(
                group_id=lesson_dict['group_id'],
                subgroup=lesson_dict['subgroup'],
                lesson_time_id=self.unique_data['lesson_times'][(lesson_dict['date'], lesson_dict['lesson_number'])],
                teacher_id=self.unique_data['teachers'][lesson_dict['teacher_fullname']],
                classroom_id=self.unique_data['classrooms'][lesson_dict['classroom_title']],
                subject_id=self.unique_data['subjects'][lesson_dict['subject_title']]
            )
            lesson_objects.append(lesson_obj)
        self.lessons = lesson_objects

    async def run(self):
        async with ClientSession() as session:
            self.session = session
            tasks = [self.process_group(group) for group in self.groups]
            await asyncio.gather(*tasks)
            if self.success_ids:
                self.collect_unique_elements()
                self.related_objects_mapping()
                self.save_to_db()

    def save_to_db(self):
        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.lessons)
                affected_entities = synchronize_lessons(self.success_ids)
                LessonBuffer.objects.all().delete()

            logger.info(f"Данные обновлены для {len(self.success_ids)} групп")
            return affected_entities

        except Exception as e:
            logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
            raise


@shared_task(bind=True, max_retries=1, default_retry_delay=60, queue='periodic_tasks')
def update_schedule(self):
    try:
        groups = Group.objects.groups_links()
        # Используем asyncio.run для запуска асинхронного кода в синхронной задаче
        asyncio.run(update_schedule_task(groups))
        logger.info(f"Обновление расписания завершено.")
    except Exception as e:
        logger.error(f"Ошибка обновления расписания: {e}")
        raise self.retry(exc=e)


async def update_schedule_task(groups):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Connection": "keep-alive"
    }
    async with ClientSession(headers=headers) as session:
        parser = ScheduleParser(groups, session)
        await parser.run()
        # parser.save_to_db()


class LessonDict:
    __slots__ = (
        '_date', 'group', '_lesson_number', 'subject_title',
        'classroom_title', 'teacher_fullname', '_subgroup'
    )

    def __init__(self, lesson_number: str | int, subject_title: str,
                 classroom_title: str, teacher_fullname: str, subgroup: str | int,
                 date: Optional[datetime.date | str] = None, group: Optional[int] = None):
        self.date = date
        self.group = group
        self.lesson_number = lesson_number
        self.subject_title = subject_title
        self.classroom_title = classroom_title
        self.teacher_fullname = teacher_fullname
        self.subgroup = subgroup

    @property
    def lesson_number(self):
        return self._lesson_number

    @lesson_number.setter
    def lesson_number(self, value: str | int):
        self._lesson_number = self.parse_numeric_value(value, min_value=1)

    @property
    def subgroup(self):
        return self._subgroup

    @subgroup.setter
    def subgroup(self, value: str | int):
        # Наиболее часто ожидается 0
        self._subgroup = value if value == 0 else self.parse_numeric_value(value, default=0)

    @staticmethod
    def parse_numeric_value(value: str | int, min_value: int = 0, max_value: int = 9, default=None) -> int:
        """
        Преобразует текст в int и проверяет на принадлежность диапазону.
        """
        try:
            value = int(value)
            if not (min_value <= value <= max_value):
                raise ValueError(f"Число {value} вне допустимого диапазона [{min_value}, {max_value}]")
            return value
        except Exception as e:
            if default is not None:
                return default
            raise ValueError(f"Некорректное числовое значение '{value}': {e}")

    @property
    def date(self):
        return self._date

    @date.setter
    def date(self, value: Optional[datetime.date | str]):
        if isinstance(value, datetime.date) or value is None:
            self._date = value
        elif isinstance(value, str):
            try:
                self._date = datetime.strptime(value.strip(), '%d.%m.%Y').date()
            except ValueError:
                raise ValueError(f"Некорректный формат даты: '{value}'. Ожидается формат 'ДД.ММ.ГГГГ'")
        else:
            raise TypeError(f"Дата должна быть datetime.date, строкой или None, получено: {type(value)}")


class PageParser:
    __slots__ = (
        'group_id', 'soup', 'current_date',
        'prev_lesson_date', 'prev_lesson_number',
        'lessons_data'
    )

    def __init__(self, group_id, html):
        self.group_id = group_id
        try:
            self.soup = BeautifulSoup(html, 'lxml')
        except Exception as e:
            raise ValueError(f"Ошибка при обработке HTML для группы {group_id}: {e}")
        self.current_date = None
        self.prev_lesson_date = None
        self.prev_lesson_number = 0
        self.lessons_data = []  # Коллекция для накопления данных уроков

    def parse(self):
        """
        Основной метод парсинга HTML-страницы.
        Проходит по строкам таблицы, извлекая данные о датах и уроках.
        """
        try:
            for row in self.soup.find_all('tr', class_='shadow'):
                cells = row.find_all('td')
                if len(cells) == 1:
                    self.current_date = self.parse_date_cell(cells[0])
                elif len(cells) == 5 and self.current_date is not None:
                    lesson_dict = self.parse_lesson_cells(cells)
                    self.validate_lesson_order(lesson_dict.lesson_number)
                    lesson_dict.date = self.current_date
                    lesson_dict.group = self.group_id
                    self.lessons_data.append(lesson_dict)
                else:
                    raise ValueError(f"Некорректная структура таблицы для группы {self.group_id}")
            return self.lessons_data
        except Exception as e:
            raise ValueError(f"Ошибка при парсинге группы {self.group_id}: {e}")

    @staticmethod
    def parse_date_cell(cell: bs4.Tag) -> datetime.date:
        """
        Парсит ячейку с датой и возвращает объект datetime.date.
        """
        try:
            date_str = cell.text.strip().split(' - ')[0]
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except Exception as e:
            raise ValueError(f"Ошибка при обработке даты: {e}")

    @staticmethod
    def parse_lesson_cells(cells: List[bs4.Tag]) -> LessonDict:
        """
        Парсит ячейки с данными урока и возвращает словарь с информацией об уроке.
        """
        try:
            return LessonDict(
                lesson_number=cells[0].text.strip(),
                subject_title=cells[1].text.strip() or 'не указано',
                classroom_title=cells[2].text.strip() or '(дист)',
                teacher_fullname=cells[3].text.strip() or 'не указано',
                subgroup=cells[4].text.strip() or 0,
            )
        except Exception as e:
            raise ValueError(f"Ошибка при обработке строки занятия: {e}")

    def validate_lesson_order(self, lesson_number: int):
        """
        Проверяет порядок уроков и смену дат, предотвращая пропуски дат.
        """
        if lesson_number < self.prev_lesson_number:
            if self.current_date == self.prev_lesson_date:
                raise ValueError("Обнаружен пропуск строки даты перед уроком.")
        self.prev_lesson_number = lesson_number
        self.prev_lesson_date = self.current_date




# def build_lesson_obj_from_data(data: dict, timeout=CACHE_TIMEOUT) -> Lesson:
#     teacher_id = get_or_create_cached_id(Teacher, {'full_name': data['teacher_name']}, timeout)
#     classroom_id = get_or_create_cached_id(Classroom, {'title': data['classroom_title']}, timeout)
#     subject_id = get_or_create_cached_id(Subject, {'title': data['subject_title']}, timeout)
#     lesson_time_id = get_or_create_cached_id(
#         LessonTime, {'date': data['date'], 'lesson_number': data['lesson_number']}, timeout
#     )
#
#     lesson = Lesson(
#         group_id=data['group_id'],
#         subgroup=data['subgroup'],
#         lesson_time_id=lesson_time_id,
#         teacher_id=teacher_id,
#         classroom_id=classroom_id,
#         subject_id=subject_id
#     )
#
#     return lesson
#
#
# def extract_lessons_data(group_id: int, soup: BeautifulSoup):
#     """Парсит данные расписания из объекта BeautifulSoup для определённой группы."""
#     lessons_data = []
#     current_date = None
#     lesson_number_pattern = re.compile(r'^[1-9]$')
#     date_pattern = re.compile(r'^\d{2}\.\d{2}\.\d{4}$')
#
#     for row in soup.find_all('tr', class_='shadow'):
#         if 'colspan' in str(row):
#             current_date = None
#             date_str = row.text.strip().split(' - ')[0]
#             if date_pattern.match(date_str):
#                 current_date = date_str
#             else:
#                 logger.warning(f"Получен неверный формат даты '{date_str}'")
#                 raise ValueError
#
#         elif current_date and row.find('td'):
#             cells = row.find_all('td')
#             if len(cells) == 5:
#                 lesson_number = cells[0].text.strip()
#                 # проверяем что номер урока 1-6
#                 if lesson_number_pattern.match(lesson_number):
#                     lessons_data.append({
#                         'date': current_date,
#                         'lesson_number': lesson_number,
#                         'subject_title': cells[1].text.strip() or 'не указано',
#                         'classroom_title': cells[2].text.strip() or '(дист)',
#                         'teacher_name': cells[3].text.strip() or 'не указано',
#                         'subgroup': cells[4].text.strip() or '0',
#                         'group_id': group_id
#                     })
#                 else:
#                     logger.warning(f"Некорректный номер урока '{lesson_number}' {current_date} для группы {group_id}.")
#
#     logger.debug(f"Выполнен парсинг для группы c ID {group_id}: получено {len(lessons_data)} уроков.")
#     return lessons_data
#
#
# @shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
# def parse_group_data(self, group_id, link):
#     url = f"{MAIN_URL}{link}"
#     try:
#         response = fetch_response_from_url(url)
#         soup = BeautifulSoup(response.content, 'lxml')
#         lessons_data = extract_lessons_data(group_id, soup)
#         return {'group_id': group_id, 'lessons_data': lessons_data}
#     except Exception as e:
#         if self.request.retries == self.max_retries:
#             logger.error(f"Не удалось получить данные для группы ID={group_id}: {str(e)}")
#             return {'group_id': group_id, 'lessons_data': None, 'error': 'final_failure'}
#         raise self.retry(exc=e)
#
#
# def update_database(groups_ids: set, lessons_data: list[Lesson]):
#     new_lessons = []
#     for lesson_data in lessons_data:
#         lesson_obj = build_lesson_obj_from_data(lesson_data)
#         if lesson_obj:
#             new_lessons.append(lesson_obj)
#
#     try:
#         with transaction.atomic():
#             LessonBuffer.objects.bulk_create(new_lessons)
#             affected_entities = synchronize_lessons(groups_ids)
#             LessonBuffer.objects.all().delete()
#
#         logger.info(f"Данные обновлены для {len(groups_ids)} групп")
#         return affected_entities
#
#     except Exception as e:
#         logger.error(f"Ошибка при обновлении данных в БД {groups_ids}: {str(e)}")
#         raise
#
#
# @shared_task(queue='periodic_tasks')
# def process_data_final(results):
#     # Обработка собранных данных
#     lessons_data = []
#     successful_group_ids = set()
#     failed_group_ids = set()
#     for result in results:
#         if result.get('error') == 'final_failure':
#             failed_group_ids.add(result['group_id'])
#         else:
#             lessons_data.extend(result['lessons_data'])
#             successful_group_ids.add(result['group_id'])
#     affected_entities = update_database(successful_group_ids, lessons_data)
#     return affected_entities
#     # if failed_group_ids:
#     #     pass
#     # Уведомляем администратора об ошибках (добавить потом)
#     # notify_admins_of_failures(failed_updates)
#     # Обрабатываем успешные результаты
#
#
# async def fetch_group_data(session: aiohttp.ClientSession, group_id: int, link: str) -> Dict[str, Any]:
#     url = f"{MAIN_URL}{link}"
#     response_text = await fetch_response_from_url(session, url)
#
#     if not response_text:
#         return {'group_id': group_id, 'error': 'fetch_failed'}
#
#     try:
#         soup = BeautifulSoup(response_text, 'lxml')
#         lessons_data = extract_lessons_data(group_id, soup)
#         return {'group_id': group_id, 'lessons_data': lessons_data}
#     except Exception as e:
#         logger.error(f"Ошибка при парсинге данных для группы {group_id}: {e}")
#         return {'group_id': group_id, 'error': 'parse_failed'}
#
#
# # Асинхронная функция для сбора данных для всех групп с ограничением на количество одновременных запросов
# async def gather_group_data(groups: List[Dict[str, Any]], max_concurrent_requests: int = 10) -> List[Dict[str, Any]]:
#     semaphore = asyncio.Semaphore(max_concurrent_requests)  # Ограничиваем количество одновременных запросов
#
#     async def bounded_fetch(session, group):
#         async with semaphore:
#             return await fetch_group_data(session, group['id'], group['link'])
#
#     async with aiohttp.ClientSession() as session:
#         tasks = [bounded_fetch(session, group) for group in groups]
#         return await asyncio.gather(*tasks)
#
# #
# @shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
# def update_schedule(self):
#     try:
#         groups = Group.objects.groups_links()
#
#         loop = asyncio.get_event_loop()
#         results = loop.run_until_complete(gather_group_data(groups))
#
#         process_data_final.delay(results)
#
#         logger.info(f"Обновление расписания завершено.")
#     except Exception as e:
#         logger.error(f"Ошибка обновления расписания: {e}")
#         raise self.retry(exc=e)
