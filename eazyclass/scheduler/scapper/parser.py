from typing import List

from scheduler.schemas import LessonParser

# TODO: возможно стоит избавиться от ScheduleDataParser и заменить на метод основного класса или класс описывающий скраппинг страницы в целом (получение html, исзвлечение и парсинг)
class ScheduleDataParser:
    def __init__(self, group_id: int, raw_lessons: List[dict]):
        self.group_id = group_id
        self.raw_lessons = raw_lessons
        self.validated_lessons = []

    def parse(self):
        for raw_lesson in self.raw_lessons:
            raw_lesson['group_id'] = self.group_id
            validate_lesson = LessonParser(**raw_lesson)
            self.validated_lessons.append(validate_lesson)
        return self.validated_lessons
