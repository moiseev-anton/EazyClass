from datetime import date as DateClass
from functools import lru_cache
from functools import partial
from typing import Any
import re
import logging

from dateparser.date import DateDataParser
from itemloaders.processors import MapCompose, TakeFirst
from scrapy.loader import ItemLoader

from scheduler.models import Subject, Classroom, Teacher

logger = logging.getLogger(__name__)

# Константы для значений по умолчанию
SUBJECT_DEFAULT_VALUE = TEACHER_DEFAULT_VALUE = 'Не указано'
CLASSROOM_DEFAULT_VALUE = '(дист)'
SUBGROUP_DEFAULT_VALUE = 0

DATE_PATTERN = r'\b\d{1,2}\.\d{1,2}\.\d{4}\b'

# Константы максимальных длин (связаны с моделями Django)
MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field('title').max_length
MAX_CLASSROOM_TITLE_LENGTH = Classroom._meta.get_field('title').max_length
MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field('full_name').max_length

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


def validate_integer(value: int, min_value: int = float('-inf'), max_value: int = float('inf')) -> int:
    """
    Проверяет, что значение является целым числом и лежит в пределах заданного диапазона.

    :param value: Число для проверки.
    :type value: int
    :param min_value: Минимально допустимое значение. По умолчанию `-inf`.
    :type min_value: int, optional
    :param max_value: Максимально допустимое значение. По умолчанию `inf`.
    :type max_value: int, optional

    :return: Проверенное значение.
    :rtype: int

    :raises ValueError: Если значение выходит за пределы указанного диапазона или диапазон задан некорректно
    """
    if min_value > max_value:
        raise ValueError(f'Недопустимое значение: min_value ({min_value}) > max_value({max_value})')

    value = int(value)
    if min_value <= value <= max_value:
        return value
    raise ValueError(f"Значение '{value}' вне допустимого диапазона [{min_value}, {max_value}].")


def replace_empty_string(value: str, default: Any = '') -> str:
    """Заменяет пустую строку на значение по умолчанию."""
    if isinstance(value, str) and value.strip() == '':
        return default
    return value


def truncate_string(value: str, max_length: int) -> str:
    """
    Ограничивает длину строки заданным максимальным значением.

    Если строка превышает максимальную длину, она будет обрезана.

    :param value: Строка, длина которой должна быть ограничена.
    :type value: str
    :param max_length: Максимальная длина строки.
    :type max_length: int

    :return: Строка с ограниченной длиной.
    :rtype: str

    :raises ValueError: Если передан недопустимый параметр `max_length`.
    """
    if max_length <= 0:
        raise ValueError(f'Недопустимое значение max_length: {max_length}')
    if len(value) > max_length:
        return value[:max_length]
    return value


def build_integer_processor(min_value=float('-inf'), max_value=float('inf')) -> MapCompose:
    """
    Строит процессор для обработки целых чисел, который выполняет проверку диапазона и преобразует значение в целое число.

    :param default: Значение по умолчанию для пустых строк. По умолчанию `0`.
    :type default: int, optional
    :param min_value: Минимально допустимое значение. По умолчанию `-inf`.
    :type min_value: int, optional
    :param max_value: Максимально допустимое значение. По умолчанию `inf`.
    :type max_value: int, optional

    :return: Процессор, который обрабатывает строку, преобразует её в целое число и проверяет на диапазон.
    :rtype: MapCompose
    """
    range_validate = partial(validate_integer, min_value=min_value, max_value=max_value)
    return MapCompose(range_validate)


def build_subgroup_processor(default: int = 0, min_value=float('-inf'), max_value=float('inf')) -> MapCompose:
    """
    Строит процессор для обработки целых чисел, который выполняет проверку диапазона и преобразует значение в целое число.

    :param default: Значение по умолчанию для пустых строк. По умолчанию `0`.
    :type default: int, optional
    :param min_value: Минимально допустимое значение. По умолчанию `-inf`.
    :type min_value: int, optional
    :param max_value: Максимально допустимое значение. По умолчанию `inf`.
    :type max_value: int, optional

    :return: Процессор, который обрабатывает строку, преобразует её в целое число и проверяет на диапазон.
    :rtype: MapCompose
    """
    replace_empty = partial(replace_empty_string, default=default)
    range_validate = partial(validate_integer, min_value=min_value, max_value=max_value)
    return MapCompose(replace_empty, range_validate)


def build_string_processor(default: str, max_length: int) -> MapCompose:
    """
    Строит процессор для обработки строк, который выполняет замену пустой строки на значение по умолчанию
    и обрезает строку до заданной длины.

    :param default: Значение по умолчанию для пустых строк.
    :type default: str
    :param max_length: Максимальная длина строки.
    :type max_length: int

    :return: Процессор, который обрабатывает строку, заменяет пустую строку и обрезает её по длине.
    :rtype: MapCompose
    """
    replace_empty = partial(replace_empty_string, default=default)
    truncate = partial(truncate_string, max_length=max_length)
    return MapCompose(str.strip, replace_empty, truncate)


class LessonLoader(ItemLoader):
    """
    Загрузчик данных для урока.

    Производит обработку и валидацию загружаемых данных.
    Поля ожидаются в виде строк.
    group_id ожидается int.
    """
    default_output_processor = TakeFirst()

    group_id_in = build_integer_processor(min_value=0)
    date_in = MapCompose(parse_date)
    subject_title_in = build_string_processor(SUBJECT_DEFAULT_VALUE, MAX_SUBJECT_TITLE_LENGTH)
    classroom_title_in = build_string_processor(CLASSROOM_DEFAULT_VALUE, MAX_CLASSROOM_TITLE_LENGTH)
    teacher_fullname_in = build_string_processor(TEACHER_DEFAULT_VALUE, MAX_TEACHER_FULLNAME_LENGTH)
    subgroup_in = build_subgroup_processor(default=0, min_value=0, max_value=9)
    lesson_number_in = build_integer_processor(min_value=1, max_value=9)

    def load_item_dict(self) -> dict:
        """Возвращает данные в целевой структуре словаря."""
        return {
            'group_id': self.get_output_value('group_id'),
            'period': {
                'lesson_number': self.get_output_value('lesson_number'),
                'date': str(self.get_output_value('date')),
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
