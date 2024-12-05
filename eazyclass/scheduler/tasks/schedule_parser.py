import asyncio
import logging
from datetime import date, datetime
# from tenacity import retry, stop_after_attempt, wait_exponential
from typing import List, Dict, Optional, Union

import aiohttp
import bs4
from aiohttp import ClientSession
from bs4 import BeautifulSoup
from celery import shared_task
from django.db import transaction
from django.db.models import Model

from scheduler.tasks.db_queries import synchronize_lessons
from scheduler.models import Group, Subject, Lesson, LessonBuffer, Classroom, Teacher, LessonTime

logger = logging.getLogger(__name__)


class MaxLengthDescriptor:
    def __init__(self, max_length: int):
        self.max_length = max_length

    def __set_name__(self, owner, name):
        """Автоматически вызывается при привязке атрибута к классу."""
        self.private_name = f"_{name}"  # Приватное имя атрибута

    def __get__(self, instance, owner):
        if instance is None:
            return self
        return getattr(instance, self.private_name, None)  # Получаем значение из instance

    def __set__(self, instance, value):
        if not isinstance(value, str):
            raise TypeError(f"Значение должно быть строкой, получено: {type(value)}")
        if len(value) > self.max_length:
            value = value[:self.max_length]
        setattr(instance, self.private_name, value)


class LessonDict:
    __slots__ = (
        '_date', 'group_id', '_lesson_number', '_subject_title',
        '_classroom_title', '_teacher_fullname', '_subgroup'
    )

    # Использование правильных импортых для моделей
    MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field('title').max_length
    MAX_CLASSROOM_TITLE_LENGTH = Classroom._meta.get_field('title').max_length
    MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field('full_name').max_length

    subject_title = MaxLengthDescriptor(max_length=MAX_SUBJECT_TITLE_LENGTH)
    classroom_title = MaxLengthDescriptor(max_length=MAX_CLASSROOM_TITLE_LENGTH)
    teacher_fullname = MaxLengthDescriptor(max_length=MAX_TEACHER_FULLNAME_LENGTH)

    def __init__(self, lesson_number: Union[str, int], subject_title: str,
                 classroom_title: str, teacher_fullname: str, subgroup: Union[str, int],
                 _date: Optional[Union[date, str]] = None, group_id: Optional[int] = None):
        self.lesson_number = lesson_number
        self.subject_title = subject_title
        self.classroom_title = classroom_title
        self.teacher_fullname = teacher_fullname
        self.subgroup = subgroup
        self.date = _date
        self.group_id = group_id

    @property
    def lesson_number(self):
        return self._lesson_number

    @lesson_number.setter
    def lesson_number(self, value: Union[str, int]):
        self._lesson_number = self.parse_numeric_value(value, min_value=1)

    @property
    def subgroup(self):
        return self._subgroup

    @subgroup.setter
    def subgroup(self, value: Union[str, int]):
        self._subgroup = value if value == 0 else self.parse_numeric_value(value, default=0)

    @staticmethod
    def parse_numeric_value(value: Union[str, int], min_value: int = 0, max_value: int = 9, default=None) -> int:
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


class RelatedObjectsMap:
    __slots__ = ('model', 'mapping', 'unmapped_keys')
    """
    Класс для управления маппингом значений на связанные объекты из базы данных.
    """

    def __init__(self, model: Model, enforce_check=True):
        self.model = model
        self.mapping = {}
        self.unmapped_keys = set()

        # Опциональная проверка содержит ли модель метод маппинга ID. По умолчанию ВКЛ
        if enforce_check and not hasattr(self.model.objects, "get_or_create_objects_map"):
            raise AttributeError(
                f"Менеджер модели '{self.model.__name__}' не реализует 'get_or_create_objects_map'"
            )

    def add(self, key: str | tuple):
        if key not in self.mapping:
            self.unmapped_keys.add(key)

    def add_set(self, keys: set[str | tuple]):
        self.unmapped_keys.update(keys)

    def map(self):
        if self.unmapped_keys:
            new_mappings = self.model.objects.get_or_create_objects_map(self.unmapped_keys)
            self.mapping.update(new_mappings)
            self.unmapped_keys.clear()

    def get_mapped(self, key: str | tuple, default=None):
        if key in self.unmapped_keys:
            self.map()
        return self.mapping.get(key, default)


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
        lesson_data.group_id = self.group_id
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
        self.semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_REQUESTS)
        self.session = None  # Сессия aiohttp
        self.failed_group_ids = set()  # ID групп, для которых не удалось распарсить данные
        self.successful_group_ids = set()  # ID групп, для которых всё прошло успешно
        self.teachers = RelatedObjectsMap(Teacher)
        self.classrooms = RelatedObjectsMap(Classroom)
        self.subjects = RelatedObjectsMap(Subject)
        self.lesson_times = RelatedObjectsMap(LessonTime)
        self.parsed_lessondict_objects = []  # Список объектов Lesson
        self.lesson_model_objects = []

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
                lessons_data = SchedulePageParser(group_id=group_dict['id'], html=content).parse()
                self.parsed_lessondict_objects.extend(lessons_data)
                self.successful_group_ids.add(group_dict['id'])
            except Exception as e:
                logger.error(f"Ошибка при обработке данных группы {group_dict['id']}: {e}")
                self.failed_group_ids.add(group_dict['id'])

    def gather_unique_elements(self):
        for lesson_dict in self.parsed_lessondict_objects:
            self.teachers.add(lesson_dict.teacher_fullname)
            self.classrooms.add(lesson_dict.classroom_title)
            self.subjects.add(lesson_dict.subject_title)
            self.lesson_times.add((lesson_dict.date, lesson_dict.lesson_number))

    def create_lesson_model_objects(self):
        for lesson_dict in self.parsed_lessondict_objects:
            lesson_obj = Lesson(
                group_id=lesson_dict.group_id,
                subgroup=lesson_dict.subgroup,
                lesson_time_id=self.lesson_times.get_mapped((lesson_dict.date, lesson_dict.lesson_number)),
                teacher_id=self.teachers.get_mapped(lesson_dict.teacher_fullname),
                classroom_id=self.classrooms.get_mapped(lesson_dict.classroom_title),
                subject_id=self.subjects.get_mapped(lesson_dict.subject_title)
            )
            self.lesson_model_objects.append(lesson_obj)
        logger.debug(f'Собрали {len(self.lesson_model_objects)} объектов уроков')

    def push_lessons_to_db(self):
        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.parsed_lessondict_objects)
                # affected_entities = synchronize_lessons(self.successful_group_ids)
                LessonBuffer.objects.all().delete()

            logger.info(f"Данные обновлены для {len(self.successful_group_ids)} групп")
            # return affected_entities

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
            self.create_lesson_objects()
            self.push_lessons_to_db()

    async def update_schedule(self):
        # Используем asyncio.run для запуска асинхронного кода
        await self.run_parsing()
        logger.debug(f'Парсинг всех страницы закончен. Получили данные для {len(self.parsed_lessondict_objects)}')
        self.process_parsed_data()


@shared_task(bind=True, max_retries=0, default_retry_delay=60, queue='periodic_tasks')
async def update_schedule(self):
    try:
        groups = Group.objects.groups_links()
        logger.debug(f'Получены данные для {len(groups)} из БД')
        if groups:
            updater = ScheduleSyncManager(groups)
            await updater.update_schedule()
        logger.info(f"Обновление расписания завершено.")
    except Exception as e:
        logger.error(f"Ошибка обновления расписания: {e}")
        raise self.retry(exc=e)

if __name__ == '__main__':
    import os

    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'eazyclass.settings')

    import django

    django.setup()
    lesson = LessonDict(1, 'asdf', 'asdf', 'asdfasdf dfsadf dsfa', 1, '24.09.1994')
    print(lesson.lesson_number)