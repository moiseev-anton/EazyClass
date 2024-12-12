import asyncio
import logging

from celery import shared_task
from django.db import transaction
from django.db.models import Model

from scheduler.models import Group, Subject, Lesson, LessonBuffer, Classroom, Teacher, LessonTime
from scheduler.scapper.extractor import SchedulePageExtractor
from scheduler.scapper.http_client import HttpClient
from scheduler.scapper.parser import ScheduleDataParser
from scheduler.tasks.db_queries import synchronize_lessons

# from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


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


class ScheduleSyncManager:
    BASE_URL = 'https://bincol.ru/rasp/'
    semaphore = asyncio.Semaphore(10)

    def __init__(self):
        self.group_configs = Group.objects.link_map()  # Список кортежей (group_id, link)
        self.failed_group_ids = set()  # ID групп, для которых не удалось выполнить скрапинг
        self.successful_group_ids = set()  # ID групп, для которых всё прошло успешно
        self.teachers = RelatedObjectsMap(Teacher, enforce_check=False)
        self.classrooms = RelatedObjectsMap(Classroom, enforce_check=False)
        self.subjects = RelatedObjectsMap(Subject, enforce_check=False)
        self.lesson_times = RelatedObjectsMap(LessonTime, enforce_check=False)
        self.scraped_lessons = []  # Список объектов LessonParser
        self.lesson_model_objects = []

    # TODO: Попробовать выделить классс Scraper, подумать как его метод будет дружить с семафором. Класс Parser заменить методом класса Scrapper
    async def scrape_group_page(self, http_client, group_id, link):
        async with self.semaphore:
            try:
                content = await http_client.fetch_page_content(link)
                raw_lessons = SchedulePageExtractor(html=content).extract()
                if raw_lessons:
                    parsed_lessons = ScheduleDataParser(group_id, raw_lessons).parse()
                self.scraped_lessons.extend(parsed_lessons)
                self.successful_group_ids.add(group_id)
            except Exception as e:
                logger.error(f"Ошибка при скрапинге страницы группы {group_id}: {e}")
                self.failed_group_ids.add(group_id)

    def gather_unique_elements(self):
        for _lesson in self.scraped_lessons:
            self.teachers.add(_lesson.teacher_fullname)
            self.classrooms.add(_lesson.classroom_title)
            self.subjects.add(_lesson.subject_title)
            self.lesson_times.add((_lesson.date, _lesson.lesson_number))

    def create_lesson_model_objects(self):
        for _lesson in self.scraped_lessons:
            lesson_obj = Lesson(
                group_id=_lesson.group_id,
                subgroup=_lesson.subgroup,
                lesson_time_id=self.lesson_times.get_mapped((_lesson.date, _lesson.lesson_number)),
                teacher_id=self.teachers.get_mapped(_lesson.teacher_fullname),
                classroom_id=self.classrooms.get_mapped(_lesson.classroom_title),
                subject_id=self.subjects.get_mapped(_lesson.subject_title)
            )
            self.lesson_model_objects.append(lesson_obj)
        logger.debug(f'Собрали {len(self.lesson_model_objects)} объектов уроков')

    def push_lessons_to_db(self):
        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.scraped_lessons)
                affected_entities = synchronize_lessons(self.successful_group_ids)
                LessonBuffer.objects.all().delete()

            logger.info(f"Данные обновлены для {len(self.successful_group_ids)} групп")
            return affected_entities

        except Exception as e:
            logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
            raise

    async def scrape_pages(self):
        async with HttpClient(base_url=self.BASE_URL) as client:
            tasks = [self.scrape_group_page(client, group_id, link) for group_id, link in self.group_configs]
            await asyncio.gather(*tasks)

    def process_parsed_data(self):
        # logger.debug('Начинается обработка полученных данных')
        if self.scraped_lessons:
            self.gather_unique_elements()
            self.create_lesson_model_objects()
            self.push_lessons_to_db()

    async def update_schedule(self):
        # Используем asyncio.run для запуска асинхронного кода
        await self.scrape_pages()
        logger.debug(f'Скрапинг всех страницы закончен. Получили данные для {len(self.scraped_lessons)}')
        self.process_parsed_data()


@shared_task(bind=True, max_retries=0, default_retry_delay=60, queue='periodic_tasks')
async def update_schedule(self):
    try:
        updater = ScheduleSyncManager()
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
