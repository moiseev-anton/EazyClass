import json
import logging

from django.db import transaction

from scheduler.models import Subject, Lesson, LessonBuffer, Classroom, Teacher, Period
from scheduler.tasks.db_queries import synchronize_lessons
from scheduler.scapper.related_objects_map import RelatedObjectsMap
from scrapy_app.eazy_scrapy.spiders.schedule_spyder import SCRAPED_LESSONS_KEY, SCRAPED_GROUPS_KEY, PAGE_HASH_KEY_PREFIX
from utils.redis_clients import get_scrapy_redis_client

logger = logging.getLogger(__name__)


class ScheduleSyncManager:
    PAGE_HASH_TIMEOUT = 86400  # 24 часа

    def __init__(self):
        self.scraped_groups = None
        self.lesson_items = None
        self.redis_client = get_scrapy_redis_client()
        self.teachers = RelatedObjectsMap(Teacher, enforce_check=False)
        self.classrooms = RelatedObjectsMap(Classroom, enforce_check=False)
        self.subjects = RelatedObjectsMap(Subject, enforce_check=False)
        self.periods = RelatedObjectsMap(Period, enforce_check=False)
        self.lesson_model_objects = []

    def update_schedule(self):
        self.fetch_data()
        if self.scraped_groups:
            self.gather_unique_elements()
            self.id_mapping()
            self.create_lesson_model_objects()
            self.push_lessons_to_db()

    def fetch_data(self):
        lessons_json = self.redis_client.get(SCRAPED_LESSONS_KEY)
        group_ids_json = self.redis_client.get(SCRAPED_GROUPS_KEY)
        if not lessons_json or not group_ids_json:
            raise ValueError("Данные для обработки отсутствуют в Redis")
        self.lesson_items = json.loads(lessons_json)  # [{lesson_dict},...]
        self.scraped_groups = json.loads(group_ids_json)  # {group_id: last_content_hash}

    def gather_unique_elements(self):
        for item in self.lesson_items:
            self.teachers.add(item['teacher_fullname'])
            self.classrooms.add(item['classroom_title'])
            self.subjects.add(item['subject_title'])
            self.periods.add((item['date'], item['lesson_number']))
        logger.debug(f"Собраны уникальные элементы для маппинга.")

    def id_mapping(self):
        """Выполняет маппинг уникальных элементов на ID."""
        self.teachers.map()
        self.classrooms.map()
        self.subjects.map()
        self.periods.map()
        logger.debug("Маппинг уникальных элементов завершен.")

    def create_lesson_model_objects(self):
        for item in self.lesson_items:
            lesson_obj = Lesson(
                group_id=item['group_id'],
                subgroup=item['subgroup'],
                period_id=self.periods.get_id((item['date'], item['lesson_number'])),
                teacher_id=self.teachers.get_id(item['teacher_fullname']),
                classroom_id=self.classrooms.get_id(item['classroom_title']),
                subject_id=self.subjects.get_id(item['subject_title'])
            )
            self.lesson_model_objects.append(lesson_obj)
        logger.debug(f'Собрали {len(self.lesson_model_objects)} объектов уроков')

    def push_lessons_to_db(self):
        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.lesson_model_objects)
                synchronize_lessons(self.scraped_groups)
                LessonBuffer.objects.all().delete()
            logger.info(f"Данные обновлены для {len(self.scraped_groups)} групп")
        except Exception as e:
            logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
            raise

    def save_page_content_hashes(self):
        # TODO: Возможно можно будет переделать на mset()
        pipe = self.redis_client.pipeline()
        for group_id, page_content_hash in self.scraped_groups.items():
            pipe.setex(f'{PAGE_HASH_KEY_PREFIX}{group_id}', self.PAGE_HASH_TIMEOUT, page_content_hash)
        pipe.execute()
