import re
from datetime import date, datetime
from functools import partial
from typing import Any

from dateparser.date import DateDataParser
from itemloaders.processors import MapCompose, TakeFirst
from scrapy.loader import ItemLoader
from w3lib.html import remove_tags

from scheduler.models import Subject, Classroom, Teacher

SUBJECT_DEFAULT_VALUE = TEACHER_DEFAULT_VALUE = 'Не указано'
CLASSROOM_DEFAULT_VALUE = '(дист)'
SUBGROUP_DEFAULT_VALUE = 0

MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field('title').max_length
MAX_CLASSROOM_TITLE_LENGTH = Classroom._meta.get_field('title').max_length
MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field('full_name').max_length

ddp = DateDataParser(
    languages=['ru'],
    settings={
        "PREFER_LOCALE_DATE_ORDER": True,
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
)


def parse_date(value: str) -> date:
    if isinstance(value, str):
        return ddp.get_date_data(value)['date_obj'].date()

class LessonLoader(ItemLoader):
    @staticmethod
    def validate_integer(value: int, min_value: int = float('-inf'), max_value: int = float('inf')) -> int:
        value = int(value)
        if min_value <= value <= max_value:
            return value
        raise ValueError(f"Значение '{value}' вне допустимого диапазона [{min_value}, {max_value}].")

    @staticmethod
    def replace_empty_string(value: str, default='') -> str:
        if value.strip() == '':
            return default
        return value

    @staticmethod
    def truncate_string(value: str, max_length: int) -> str:
        if len(value) > max_length:
            return value[:max_length]
        return value

    @staticmethod
    def build_integer_processor(default: int = '', min_value=float('-inf'), max_value=float('inf')) -> MapCompose:
        range_validate = partial(LessonLoader.validate_integer, min_value=min_value, max_value=max_value)
        replace_empty = partial(LessonLoader.replace_empty_string, default=default)
        return MapCompose(remove_tags, replace_empty, int, range_validate)

    @staticmethod
    def build_string_processor(default: str, max_length: int) -> MapCompose:
        replace_empty = partial(LessonLoader.replace_empty_string, default=default)
        truncate = partial(LessonLoader.truncate_string, max_length=max_length)
        return MapCompose(remove_tags, str.strip, replace_empty, truncate)


    @staticmethod
    def parse_date(value: Any) -> date:
        if isinstance(value, str):
            for fmt in DATE_FORMATS:
                try:
                    return datetime.strptime(value.strip(), fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"Некорректный формат даты: '{value}'. Ожидается один из форматов: {DATE_FORMATS}")
        if isinstance(value, date):
            return value
        raise TypeError(f"Ожидалось строковое представление даты или объект date, получено: {type(value)}")

    default_output_processor = TakeFirst()
    # Настройка процессоров
    group_id_in = build_integer_processor(min_value=0)
    date_in = MapCompose(remove_tags, date_extract, parse_date)
    date_in = MapCompose(remove_tags, parse_date)
    subject_title_in = build_string_processor(SUBJECT_DEFAULT_VALUE, MAX_SUBJECT_TITLE_LENGTH)
    classroom_title_in = build_string_processor(CLASSROOM_DEFAULT_VALUE, MAX_CLASSROOM_TITLE_LENGTH)
    teacher_fullname_in = build_string_processor(TEACHER_DEFAULT_VALUE, MAX_TEACHER_FULLNAME_LENGTH)
    subgroup_in = build_integer_processor(default=0, min_value=0, max_value=9)
    lesson_number_in = build_integer_processor(min_value=1, max_value=9)


if __name__ == '__main__':
    pass
