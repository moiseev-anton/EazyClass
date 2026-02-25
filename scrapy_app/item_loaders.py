from datetime import date as DateClass
from functools import lru_cache
from functools import partial
from typing import Any
import re
import logging

from dateparser.date import DateDataParser
from itemloaders.processors import MapCompose, TakeFirst
from scrapy.loader import ItemLoader
from enums import Defaults

from scheduler.models import Subject, Classroom, Teacher

logger = logging.getLogger(__name__)


DATE_PATTERN = r'\b\d{1,2}\.\d{1,2}\.\d{4}\b'

date_parser = DateDataParser(
    languages=['ru'],
    settings={
        "PREFER_LOCALE_DATE_ORDER": True,
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
)


@lru_cache(maxsize=32)
def parse_date(value: str) -> DateClass:
    """
    Преобразует строковое представление даты в объект `date`.

    Если не удалось распознать дату с первого раза, пытается извлечь её с помощью регулярного выражения.

    Если переданный аргумент уже является объектом `date`, возвращается он сам.

    Кеширует результат преобразования для повторно используемых строковых значений.
    """
    if isinstance(value, str):
        try:
            # Первая попытка парсинга
            return date_parser.get_date_data(value.strip())['date_obj'].date()
        except (AttributeError, TypeError):
            logger.warning(f'Замечена нестандартная стока даты: {value}')
            # Попробуем извлечь дату с помощью регулярного выражения
            match = re.search(DATE_PATTERN, value)
            if match:
                value = match.group(0)
                # Вторая попытка парсинга после извлечения
                return date_parser.get_date_data(value)['date_obj'].date()
            raise ValueError(f"Не удалось извлечь дату из строки: {value}")

    if isinstance(value, DateClass):
        return value

    raise TypeError(f"Ожидалось строковое представление даты или объект date, получено: {type(value)}")


def normalize_html_text(value) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def normalize_int(value, min_value=float('-inf'), max_value=float('inf')) -> int:
    """
    Нормализует обязательное целое значение.

    - пустые значения запрещены
    - приводит к int
    - проверяет диапазон
    """
    if value is None:
        raise ValueError("Ожидалось целое число, получено None")

    if isinstance(value, str):
        value = value.strip()
        if value == '':
            raise ValueError("Пустая строка недопустима для целого значения")

    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Невозможно привести к int: {value!r}")

    if not (min_value <= value <= max_value):
        raise ValueError(f"Значение '{value}' вне диапазона [{min_value}, {max_value}]")

    return value


def normalize_optional_int(value, min_value=float('-inf'), max_value=float('inf')) -> int | None:
    """
    Нормализует необязательное целое значение.

    - None или пустая строка → None
    - иначе → normalize_int
    """
    if value is None:
        return None

    if isinstance(value, str) and value.strip() == '':
        return None

    return normalize_int(value, min_value=min_value, max_value=max_value)

def required_int_processor(min_value=float('-inf'), max_value=float('inf')):
    return MapCompose(partial(normalize_int, min_value=min_value, max_value=max_value))

def optional_int_processor(min_value=float('-inf'), max_value=float('inf')):
    return MapCompose(partial(normalize_optional_int, min_value=min_value, max_value=max_value))


class LessonLoader(ItemLoader):
    """
    Загрузчик данных для урока.

    Производит обработку и валидацию загружаемых данных.
    Поля ожидаются в виде строк.
    group_id ожидается int.
    """
    default_output_processor = TakeFirst()

    group_id_in = required_int_processor(0)
    date_in = MapCompose(parse_date)
    subject_title_in = MapCompose(normalize_html_text)
    classroom_title_in = MapCompose(normalize_html_text)
    teacher_fullname_in = MapCompose(normalize_html_text)
    subgroup_in = optional_int_processor(0, 9)
    lesson_number_in = required_int_processor(0, 9)

    def load_item_dict(self) -> dict:
        """Возвращает данные в целевой структуре словаря."""
        return {
            'group_id': self.get_output_value('group_id'),
            'period': {
                'lesson_number': self.get_output_value('lesson_number'),
                'date': self.get_output_value('date'),
            },
            'subject': {
                'title': self.get_output_value('subject_title'),
            },
            'classroom': {
                'title': self.get_output_value('classroom_title'),
            },
            'teacher': {
                'full_name': self.get_output_value('teacher_fullname'),
            },
            'subgroup': self.get_output_value('subgroup'),
        }
