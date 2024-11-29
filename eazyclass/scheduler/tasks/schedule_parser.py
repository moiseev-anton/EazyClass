import asyncio
import logging
import random
from collections import defaultdict
from datetime import datetime, date

import aiohttp
# from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict, Optional, Union

import bs4
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction, models

from .db_queries import synchronize_lessons
from ..models import Group, Subject, Lesson, LessonBuffer, Classroom, Teacher, LessonTime

logger = logging.getLogger(__name__)


class LessonDict:
    __slots__ = (
        '_date', 'group', '_lesson_number', '_subject_title',
        '_classroom_title', '_teacher_fullname', '_subgroup'
    )

    MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field('title').max_length
    MAX_CLASSROOM_TITLE_LENGTH = Teacher._meta.get_field('title').max_length
    MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field('full_name').max_length

    def __init__(self, lesson_number: str | int, subject_title: str,
                 classroom_title: str, teacher_fullname: str, subgroup: str | int,
                 _date: Optional[date | str] = None, group: Optional[int] = None):
        self.date = _date
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
    def date(self) -> Optional[date]:
        return self._date

    @date.setter
    def date(self, value: Optional[Union[date, str]]) -> None:
        if isinstance(value, date) or value is None:
            self._date = value
        elif isinstance(value, str):
            try:
                self._date = datetime.strptime(value.strip(), '%d.%m.%Y').date()
            except ValueError:
                raise ValueError(f"Некорректный формат даты: '{value}'. Ожидается формат 'ДД.ММ.ГГГГ'")
        else:
            raise TypeError(f"Дата должна быть типа date, строкой или None, получено: {type(value)}")

    @property
    def subject_title(self) -> str:
        return self._subject_title

    @subject_title.setter
    def subject_title(self, value: str):
        self._subject_title = self.validate_string_value(value, self.MAX_SUBJECT_TITLE_LENGTH)

    @property
    def classroom_title(self) -> str:
        return self._classroom_title

    @classroom_title.setter
    def classroom_title(self, value: str):
        self._classroom_title = self.validate_string_value(value, self.MAX_CLASSROOM_TITLE_LENGTH)

    @property
    def teacher_fullname(self) -> str:
        return self._teacher_fullname

    @teacher_fullname.setter
    def teacher_fullname(self, value: str):
        self._teacher_fullname = self.validate_string_value(value, self.MAX_TEACHER_FULLNAME_LENGTH)

    @staticmethod
    def validate_string_value(value: str, max_length: int) -> str:
        """
        Проверяет, что строка соответствует ограничениям длины из модели БД.
        """
        if not isinstance(value, str):
            raise TypeError(f"Значение должно быть строкой, получено: {type(value)}")
        if len(value) > max_length:
            value = value[:max_length]
        return value


class RelatedObjectsMap(dict):
    def __init__(self, model: models.Model):
        super().__init__()
        self.model = model
        self.unmapped_keys = set()

    def add(self, key):
        if key not in self:
            self.unmapped_keys.add(key)

    def add_many(self, keys):
        for key in keys:
            self.add(key)

    def map(self):
        if self.unmapped_keys:
            new_mappings = self.model.objects.get_or_create_objects_map(self.unmapped_keys)
            self.update(new_mappings)
            self.unmapped_keys.clear()

    def get(self, key, default=None):
        if key in self.unmapped_keys:
            self.map()
        return super().get(key, default)


class SchedulePageParser:
    DATE_ROW_LENGTH = 1
    LESSON_ROW_LENGTH = 5

    __slots__ = (
        'group_id', 'soup', 'current_date',
        'prev_lesson_date', 'prev_lesson_number',
        'lessons_data', 'validate_order'
    )

    def __init__(self, group_id, html, validate_order: bool = False):
        self.group_id = group_id
        self.soup = BeautifulSoup(html, 'lxml')
        self.current_date = None
        self.prev_lesson_date = None
        self.prev_lesson_number = 0
        self.lessons_data = []  # Список для хранения уроков
        self.validate_order = validate_order

    def parse(self) -> List[LessonDict]:
        """
        Основной метод парсинга HTML-страницы.
        Проходит по строкам таблицы, извлекая данные о датах и уроках.
        """
        for row in self.soup.find_all('tr', class_='shadow'):
            cells = row.find_all('td')
            if len(cells) == self.DATE_ROW_LENGTH:
                self._parse_date(cells)
            elif len(cells) == self.LESSON_ROW_LENGTH and self.current_date is not None:
                self._parse_lesson(cells)
            else:
                raise ValueError(f"Некорректная структура таблицы для группы {self.group_id}")
        return self.lessons_data

    def _parse_lesson(self, cells: List[bs4.Tag]) -> None:
        lesson_data = self._extract_lesson_data(cells)
        if self.validate_order:
            self._validate_lesson_order(lesson_data.lesson_number)
        lesson_data.date = self.current_date
        lesson_data.group = self.group_id
        self.lessons_data.append(lesson_data)

    def _parse_date(self, cells: List[bs4.Tag]) -> datetime.date:
        self.current_date = self._extract_date(cells[0])

    @staticmethod
    def _extract_date(cell: bs4.Tag) -> datetime.date:
        """Извлекает дату из ячейки таблицы и возвращает объект datetime.date."""
        try:
            date_str = cell.text.strip().split(' - ')[0]
            return datetime.strptime(date_str, '%d.%m.%Y').date()
        except ValueError as e:
            raise ValueError(f"Ошибка при обработке даты: {e}")

    @staticmethod
    def _extract_lesson_data(cells: List[bs4.Tag]) -> LessonDict:
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

    def _validate_lesson_order(self, lesson_number: int) -> None:
        """
        Проверяет порядок уроков и смену дат, предотвращая пропуски дат.
        """
        if lesson_number < self.prev_lesson_number:
            if self.current_date == self.prev_lesson_date:
                raise ValueError("Обнаружен пропуск строки даты перед уроком")
        self.prev_lesson_number = lesson_number
        self.prev_lesson_date = self.current_date


class ScheduleSyncManager:
    MAX_CONCURRENT_REQUESTS = 10
    BASE_URL = 'https://bincol.ru/rasp/'
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Connection": "keep-alive"
    }

    def __init__(self, group_configs: List[Dict]):
        self.group_configs = group_configs  # Список словарей с id и link групп
        self.session = None  # Сессия aiohttp
        self.parsed_lessons = []  # Список объектов Lesson
        self.failed_group_ids = set()  # ID групп, для которых не удалось распарсить данные
        self.successful_group_ids = set()  # ID групп, для которых всё прошло успешно
        self.unique_elements = defaultdict(set)
        self.related_mappings = {}
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)

    # @retry(
    #     stop=stop_after_attempt(3),  # Максимум 3 попытки
    #     wait=wait_exponential(multiplier=1, min=1, max=4),  # Экспоненциальная задержка
    #     reraise=True  # Исключение будет выброшено после всех неудачных попыток
    # )
    async def fetch_page_content(self, url: str) -> str:
        logger.debug(f'Отправка запроса к {url}')
        async with self.session.get(url) as response:
            if response.status != 200:
                logger.warning(f"Ошибка получения html со страницы: {response.status}")
                raise ValueError(f"Неверный код ответа: {response.status}")
            return await response.text()

    async def fetch_group_page_content(self, link: str):
        # await asyncio.sleep(random.uniform(0.5, 2))
        return await self.fetch_page_content(link)

    async def process_group_page(self, group_dict):
        async with self.semaphore:
            try:
                content = await self.fetch_group_page_content(group_dict['link'])
                logger.debug(f'Получили html для группы {group_dict['link']}')
                lessons_data = SchedulePageParser(group_id=group_dict['id'], html=content).parse()
                logger.debug(f'Распарсили уроки для гуппы {group_dict['link']}')
                self.parsed_lessons.extend(lessons_data)
                self.successful_group_ids.add(group_dict['id'])
            except Exception as e:
                logger.error(f"Ошибка при обработке данных группы {group_dict['id']}: {e}")
                self.failed_group_ids.add(group_dict['id'])

    def gather_unique_elements(self):
        # TODO: возможно можно на этом этапе использовать кеш
        for lesson_dict in self.parsed_lessons:
            self.unique_elements['teachers'].add(lesson_dict.teacher_fullname)
            self.unique_elements['classrooms'].add(lesson_dict.classroom_title)
            self.unique_elements['subjects'].add(lesson_dict.subject_title)
            self.unique_elements['lesson_times'].add((lesson_dict.date, lesson_dict.lesson_number))
        logger.debug(f'Собрано множество из {len(self.unique_elements['teachers'])} учителей')
        logger.debug(f'Собрано множество из {len(self.unique_elements['classrooms'])} кабинетов')
        logger.debug(f'Собрано множество из {len(self.unique_elements['subjects'])} предметов')
        logger.debug(f'Собрано множество из {len(self.unique_elements['lesson_times'])} звонков')

    def map_related_objects(self):
        self.related_mappings['teachers'] = Teacher.objects.get_or_create_map(self.unique_elements['teachers'])
        self.related_mappings['classrooms'] = Classroom.objects.get_or_create_map(self.unique_elements['classrooms'])
        self.related_mappings['subjects'] = Subject.objects.get_or_create_map(self.unique_elements['subjects'])
        self.related_mappings['lesson_times'] = LessonTime.objects.get_or_create_map(
            self.unique_elements['lesson_times'])

    def create_lesson_objects(self):
        lesson_objects = []
        for lesson_dict in self.parsed_lessons:
            # TODO: рассмотреть применение get() для словарей на всякий случай
            lesson_obj = Lesson(
                group_id=lesson_dict.group,
                subgroup=lesson_dict.subgroup,
                lesson_time_id=self.related_mappings['lesson_times'][(lesson_dict.date, lesson_dict.lesson_number)],
                teacher_id=self.related_mappings['teachers'][lesson_dict.teacher_fullname],
                classroom_id=self.related_mappings['classrooms'][lesson_dict.classroom_title],
                subject_id=self.related_mappings['subjects'][lesson_dict.subject_title]
            )
            lesson_objects.append(lesson_obj)
        self.parsed_lessons = lesson_objects
        logger.debug(f'Собрали {len(self.parsed_lessons)} объектов уроков')

    def push_lessons_to_db(self):
        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.parsed_lessons)
                affected_entities = synchronize_lessons(self.successful_group_ids)
                LessonBuffer.objects.all().delete()

            logger.info(f"Данные обновлены для {len(self.successful_group_ids)} групп")
            return affected_entities

        except Exception as e:
            logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
            raise

    async def run_parsing(self):
        timeout = aiohttp.ClientTimeout(total=60, connect=10)
        async with ClientSession(base_url=self.BASE_URL, timeout=timeout) as session:
            logger.debug('Создали сессию')
            self.session = session
            await self.fetch_page_content('')
            logger.debug('Главная страница доступна')
            tasks = [self.process_group_page(group) for group in self.group_configs]
            await asyncio.gather(*tasks)

    def process_parsed_data(self):
        logger.debug('Начинается обработка полученных данных')
        if self.successful_group_ids:
            self.gather_unique_elements()
            self.map_related_objects()
            self.create_lesson_objects()
            self.push_lessons_to_db()

    def update_schedule(self):
        # Используем asyncio.run для запуска асинхронного кода
        asyncio.run(self.run_parsing())
        logger.debug(f'Парсинг всех страницы закончен. Получили данные для {len(self.parsed_lessons)}')
        self.process_parsed_data()


@shared_task(bind=True, max_retries=0, default_retry_delay=60, queue='periodic_tasks')
def update_schedule(self):
    try:
        groups = Group.objects.groups_links()
        logger.debug(f'Получены данные для {len(groups)} из БД')
        if groups:
            updater = ScheduleSyncManager(groups)
            updater.update_schedule()
        logger.info(f"Обновление расписания завершено.")
    except Exception as e:
        logger.error(f"Ошибка обновления расписания: {e}")
        raise self.retry(exc=e)
