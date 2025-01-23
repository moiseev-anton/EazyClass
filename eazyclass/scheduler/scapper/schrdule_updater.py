import datetime
import json
import logging

from bulk_sync import bulk_sync, bulk_compare
from django.db import transaction

from scheduler.models import Subject, Lesson, LessonBuffer, Classroom, Teacher, Period
from scheduler.tasks.db_queries import synchronize_lessons
from scheduler.scapper.related_objects_map import RelatedObjectsMap
from scrapy_app.spiders import SCRAPED_LESSONS_KEY, SCRAPED_GROUPS_KEY, PAGE_HASH_KEY_PREFIX
from utils import RedisClientManager

logger = logging.getLogger(__name__)


class ScheduleSyncManager:
    PAGE_HASH_TIMEOUT = 86400  # 24 часа
    COMPRASION_FIELDS = ['group_id', 'period_id', 'subject_id', 'classroom_id', 'teacher_id', 'subgroup']

    def __init__(self):
        self.scraped_groups = None  # {group_id: page_hash, ...}
        self.lesson_items = None  # [{lesson_dict}, ...]
        self.redis_client = RedisClientManager.get_client('scrapy')
        self.teachers = RelatedObjectsMap(Teacher, ('full_name', ))
        self.classrooms = RelatedObjectsMap(Classroom, ('title', ))
        self.subjects = RelatedObjectsMap(Subject, ('title', ))
        self.periods = RelatedObjectsMap(Period, ('date', 'lesson_number'))
        self.lesson_model_objects = []

    def update_schedule(self):
        self.fetch_data()
        if self.scraped_groups:
            if self.lesson_items:
                self.gather_unique_elements()
                self.id_mapping()
                self.create_lesson_model_objects()
            self.push_lessons_to_db()
            self.cache_page_content_hashes()

    def fetch_data(self):
        lessons_json = self.redis_client.get(SCRAPED_LESSONS_KEY)
        group_ids_json = self.redis_client.get(SCRAPED_GROUPS_KEY)
        if not lessons_json or not group_ids_json:
            raise ValueError("Данные для обработки отсутствуют в Redis")
        self.lesson_items = json.loads(lessons_json)  # [{lesson_dict},...]
        self.scraped_groups = json.loads(group_ids_json)  # {group_id: last_content_hash}

    def gather_unique_elements(self):
        for item in self.lesson_items:
            self.teachers.add(item['teacher'])
            self.classrooms.add(item['classroom'])
            self.subjects.add(item['subject'])
            self.periods.add(item['period'])
        logger.debug(f"Собраны уникальные элементы для маппинга.")

    def id_mapping(self):
        """Выполняет маппинг уникальных элементов на ID."""
        self.teachers.resolve_pending_keys()
        self.classrooms.resolve_pending_keys()
        self.subjects.resolve_pending_keys()
        self.periods.resolve_pending_keys()
        logger.debug("Маппинг уникальных элементов завершен.")

    def create_lesson_model_objects(self):
        for item in self.lesson_items:
            if item['group_id'] in self.scraped_groups:
                lesson_obj = Lesson(
                    group_id=item['group_id'],
                    subgroup=item['subgroup'],
                    period_id=self.periods.get_or_map_id(item['period']),
                    teacher_id=self.teachers.get_or_map_id(item['teacher']),
                    classroom_id=self.classrooms.get_or_map_id(item['classroom']),
                    subject_id=self.subjects.get_or_map_id(item['subject'])
                )
                self.lesson_model_objects.append(lesson_obj)
        logger.debug(f'Собрали {len(self.lesson_model_objects)} объектов уроков')

    def push_lessons_to_db(self):
        """Синхронизация через буферную таблицу в БД.
        Используется raw SQL
        """
        try:
            with transaction.atomic():
                LessonBuffer.objects.bulk_create(self.lesson_model_objects)
                synchronize_lessons(self.scraped_groups.keys())
                LessonBuffer.objects.all().delete()
            logger.info(f"Данные обновлены для {len(self.scraped_groups)} групп")
        except Exception as e:
            logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
            raise

    def schedule_bulk_sync(self):
        """Синхронизация всех уроков с БД за 1 запрос.
         Но не можем узнать какие уроки были изменениы, добавлены или удалены.
         Придется полагаться только на триггеры в БД.
        Для каждой отдельно операции записи трггер быдет вызвывать функцию, что не оптимально
        """
        periods = Period.objects.filter(date__gte=datetime.date.today())  # Только для записей с датой >= сегодня

        with transaction.atomic():
            synced_lessons = bulk_sync(
                new_models=self.lesson_model_objects,
                filters={
                    'period__in': periods,  # Фильтруем по периодам
                    'group__in': self.scraped_groups.keys(),  # Фильтруем по успешным группам
                    'is_active': True  # Фильтруем только активные уроки
                },
                key_fields=["group_id", "period", "subgroup"],  # Множество ключевых полей
            )

        return synced_lessons

    def synchronize_lessons_by_compare(self):
        """Ручное управление синхронизацией.
        Сепарируем объекты Lesson по группам. to_create, to_update, to_delete.

        """
        periods = Period.objects.filter(date__gte=datetime.date.today())
        new_lessons = self.lesson_model_objects
        groups = self.scraped_groups.keys()
        existing_lessons = Lesson.objects.filter(period__in=periods, group__in=groups, is_active=True)

        comparison_result = bulk_compare(
            new_models=new_lessons,
            old_models=existing_lessons,
            key_fields=self.COMPRASION_FIELDS,
        )

        to_create = comparison_result['added']
        to_update = comparison_result['updated']
        to_delete = comparison_result['removed']

        if to_delete:
            Lesson.objects.bulk_delete(to_delete)

        if to_update:
            Lesson.objects.bulk_update(to_update, fields=self.COMPRASION_FIELDS)

        if to_create:
            Lesson.objects.bulk_create(to_create)

    def cache_page_content_hashes(self):
        pipe = self.redis_client.pipeline()
        for group_id, page_content_hash in self.scraped_groups.items():
            pipe.setex(f'{PAGE_HASH_KEY_PREFIX}{group_id}', self.PAGE_HASH_TIMEOUT, page_content_hash)
        pipe.execute()
