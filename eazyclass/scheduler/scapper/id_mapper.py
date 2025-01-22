import logging

from scheduler.models import Subject, Classroom, Teacher, Period
from scheduler.scapper.related_objects_map import RelatedObjectsMap

logger = logging.getLogger(__name__)


class IdMapper:
    def __init__(self, lesson_items: list[dict]):
        self.lesson_items = lesson_items  # [{lesson_dict}, ...]
        self.teachers = RelatedObjectsMap(Teacher, ['full_name', ])
        self.classrooms = RelatedObjectsMap(Classroom, ['title', ])
        self.subjects = RelatedObjectsMap(Subject, ['title', ])
        self.periods = RelatedObjectsMap(Period, ['date', 'lesson_number'])

    def map(self):
        self.gather_unique_elements()
        self.id_mapping()

    def gather_unique_elements(self):
        for item in self.lesson_items:
            self.teachers.add(item['teacher'])
            self.classrooms.add(item['classroom'])
            self.subjects.add(item['subject'])
            self.periods.add(item['period'])
        logger.debug(f"Собраны уникальные элементы для маппинга.")

    def id_mapping(self):
        """Выполняет маппинг уникальных элементов на ID."""
        self.teachers.map()
        self.classrooms.map()
        self.subjects.map()
        self.periods.map()
        logger.debug("Маппинг уникальных элементов завершен.")
