import logging
import pickle
from datetime import date
from typing import Optional, Dict, List, Any

from bulk_sync import bulk_compare as original_bulk_compare
from django.db import transaction

from scheduler.models import Subject, Lesson, Classroom, Teacher, Period
from scheduler.scrapied_data_sync.related_objects_map import RelatedObjectsMap
from scrapy_app.spiders import SCRAPED_LESSONS_KEY, SCRAPED_GROUPS_KEY, PAGE_HASH_KEY_PREFIX
from utils import RedisClientManager

logger = logging.getLogger(__name__)

SCHEDULE_CHANGES_KEY = 'shedule_changes'


class ScheduleSyncManager:
    PAGE_HASH_TIMEOUT: int = 86400  # 24 часа
    SCHEDULE_CHANGES_TIMEOUT: int = 3600  # 1 час
    COMPARISON_FIELDS: List[str] = ['group_id', 'period_id', 'subgroup']
    UPDATE_FIELDS: List[str] = ['subject_id', 'classroom_id', 'teacher_id']

    def __init__(self):
        self.scraped_groups: Optional[Dict[int, str]] = None  # {group_id: page_hash, ...}
        self.lesson_items: Optional[List[Dict[str, Any]]] = None  # [{lesson_dict}, ...]
        self.comparison_result: Optional[Dict[str, List[Any]]] = None
        self.redis_client = RedisClientManager.get_client('scrapy')
        self.teachers = RelatedObjectsMap(Teacher, ('full_name',))
        self.classrooms = RelatedObjectsMap(Classroom, ('title',))
        self.subjects = RelatedObjectsMap(Subject, ('title',))
        self.periods = RelatedObjectsMap(Period, ('date', 'lesson_number'))
        self.new_lessons: List[Lesson] = []
        self.start_sync_day: date = date.today()

    def update_schedule(self) -> None:
        """Обновляет расписание, получая данные, обрабатывая их и сохраняя результат."""
        self.fetch_data()
        if self.scraped_groups:
            if self.lesson_items:
                self._process_lessons()
            self.save_sync_result_to_redis()

    def _process_lessons(self) -> None:
        """Обрабатывает уроки:
        собирает уникальные элементы,
        маппит ID,
        создает новые уроки,
        сравнивает c уроками в БД,
        применяет изменения.
        """
        self.gather_unique_elements()
        self.id_mapping()
        self._create_new_lessons()
        self._compare_lessons()
        self.apply_changes_to_db()

    def fetch_data(self) -> None:
        """Получает данные из Redis и десериализует их."""
        logger.info("Пробуем получить данные из Redis")
        lessons_pickle = self.redis_client.get(SCRAPED_LESSONS_KEY)
        group_ids_pickle = self.redis_client.get(SCRAPED_GROUPS_KEY)
        if not lessons_pickle or not group_ids_pickle:
            raise ValueError("Данные для обработки отсутствуют в Redis")
        self.lesson_items = pickle.loads(lessons_pickle)  # [{lesson_dict},...]
        self.scraped_groups = pickle.loads(group_ids_pickle)  # {group_id: last_content_hash}
        logger.info("Получили данные из Redis")

    def gather_unique_elements(self) -> None:
        """Собирает уникальные элементы (учителей, кабинеты, предметы, периоды) для маппинга."""
        for item in self.lesson_items:
            self.teachers.add(item['teacher'])
            self.classrooms.add(item['classroom'])
            self.subjects.add(item['subject'])
            self.periods.add(item['period'])
        logger.info(f"Собраны уникальные элементы для маппинга.")
        logger.info(f'Собрано уникальных периодов {len(self.periods.pending_keys)}')
        logger.info(f'Собрано уникальных учителей {len(self.teachers.pending_keys)}')
        logger.info(f'Собрано уникальных предметов {len(self.subjects.pending_keys)}')
        logger.info(f'Собрано уникальных кабинетов {len(self.classrooms.pending_keys)}')

    def id_mapping(self) -> None:
        """Выполняет маппинг уникальных элементов на их ID в БД."""
        self.teachers.resolve_pending_keys()
        self.classrooms.resolve_pending_keys()
        self.subjects.resolve_pending_keys()
        self.periods.resolve_pending_keys()
        logger.debug("Маппинг уникальных элементов завершен.")
        logger.info(f'Получено id периодов {len(self.periods.existing_mappings)}')
        logger.info(f'id периодов {self.periods.existing_mappings}')

        logger.info(f'Получено id учителей {len(self.teachers.existing_mappings)}')
        logger.info(f'Получено id предметов {len(self.subjects.existing_mappings)}')
        logger.info(f'Получено id кабинетов {len(self.classrooms.existing_mappings)}')

    def _create_new_lessons(self) -> None:
        """Создает объекты уроков на основе полученных данных."""
        for item in self.lesson_items:
            if item['group_id'] in self.scraped_groups and item['period']['date'] >= self.start_sync_day:
                lesson_obj = Lesson(
                    group_id=item['group_id'],
                    subgroup=item['subgroup'],
                    period_id=self.periods.get_or_map_id(item['period']),
                    teacher_id=self.teachers.get_or_map_id(item['teacher']),
                    classroom_id=self.classrooms.get_or_map_id(item['classroom']),
                    subject_id=self.subjects.get_or_map_id(item['subject'])
                )
                self.new_lessons.append(lesson_obj)
        logger.debug(f'Собрали {len(self.new_lessons)} объектов уроков')

    def _compare_lessons(self) -> None:
        """Сравнивает новые уроки с текущими в БД и сохраняет результат."""
        periods = Period.objects.filter(date__gte=self.start_sync_day)
        groups = self.scraped_groups.keys()
        existing_lessons = Lesson.objects.filter(period__in=periods, group__in=groups, is_active=True)

        self.comparison_result = self.bulk_compare(
            new_models=self.new_lessons,
            old_models=existing_lessons,
            key_fields=self.COMPARISON_FIELDS,
        )

    def apply_changes_to_db(self) -> None:
        """Применяет изменения в БД в рамках транзакции."""
        if not self.comparison_result:
            logger.warning("Нет данных для синхронизации")
            return

        lessons_to_delete = self.comparison_result['removed']
        lessons_to_update = self.comparison_result['updated']
        lessons_to_create = self.comparison_result['added']

        logger.info(f'Уроков для удаления ({len(lessons_to_delete)})')
        logger.info(f'Уроков для обновления ({len(lessons_to_update)})')
        logger.info(f'Уроков для создания ({len(lessons_to_create)})')

        with transaction.atomic():
            if lessons_to_delete:
                Lesson.objects.filter(id__in=[lesson.id for lesson in lessons_to_delete]).delete()

            if lessons_to_update:
                Lesson.objects.bulk_update(lessons_to_update, fields=self.UPDATE_FIELDS)

            if lessons_to_create:
                Lesson.objects.bulk_create(lessons_to_create)

        logger.info("Синхронизация занятий с БД произведена")

    def save_sync_result_to_redis(self) -> None:
        """
        Сохраняет результаты синхронизации в Redis в рамках redis pipeline.
        Сперва сохраняет изменения расписания.
        Затем сохраняет хеши содержимого веб-страниц данные которых синхронизированы с БД.
        """
        if not self.comparison_result:
            logger.warning("Нет данных для сохранения в Redis")
            return

        serialized_result = pickle.dumps(self.comparison_result)
        with self.redis_client.pipeline() as pipe:
            pipe.setex(SCHEDULE_CHANGES_KEY, self.SCHEDULE_CHANGES_TIMEOUT, serialized_result)

            for group_id, page_content_hash in self.scraped_groups.items():
                pipe.setex(f'{PAGE_HASH_KEY_PREFIX}{group_id}', self.PAGE_HASH_TIMEOUT, page_content_hash)

            pipe.execute()

        logger.info(f"Результат синхронизации сохранен в Redis")

    @staticmethod
    def bulk_compare(*args, **kwargs) -> Dict[str, List[Any]]:
        """Обертка над bulk_compare, которая приводит removed: odict_values к списку."""
        result = original_bulk_compare(*args, **kwargs)
        return {
            'added': result['added'],
            'updated': result['updated'],
            'removed': list(result['removed']),
        }

    # def push_lessons_to_db(self):
    #     """Синхронизация через буферную таблицу в БД.
    #     Используется raw SQL
    #     """
    #     try:
    #         with transaction.atomic():
    #             LessonBuffer.objects.bulk_create(self.lesson_model_objects)
    #             synchronize_lessons(self.scraped_groups.keys())
    #             LessonBuffer.objects.all().delete()
    #         logger.info(f"Данные обновлены для {len(self.scraped_groups)} групп")
    #     except Exception as e:
    #         logger.error(f"Ошибка при обновлении данных в БД: {str(e)}")
    #         raise
    #
    # def schedule_bulk_sync(self):
    #     """Синхронизация всех уроков с БД за 1 запрос.
    #      Но не можем узнать какие уроки были изменениы, добавлены или удалены.
    #      Придется полагаться только на триггеры в БД.
    #     Для каждой отдельной записи триггер будет вызывать функцию, что не оптимально
    #     """
    #     periods = Period.objects.filter(date__gte=self.start_sync_day)  # Только для записей с датой >= start_sync_day(сегодня)
    #
    #     with transaction.atomic():
    #         synced_lessons = bulk_sync(
    #             new_models=self.lesson_model_objects,
    #             filters={
    #                 'period__in': periods,  # Фильтруем по периодам
    #                 'group__in': self.scraped_groups.keys(),  # Фильтруем по успешным группам
    #                 'is_active': True  # Фильтруем только активные уроки
    #             },
    #             key_fields=["group_id", "period", "subgroup"],  # Множество ключевых полей
    #         )
    #
    #     return synced_lessons
