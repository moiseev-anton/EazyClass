from contextlib import nullcontext as does_not_raise
from datetime import date as DateClass

import pytest

from scrapy_app.item_loaders import (
    LessonLoader,
    parse_date,
    validate_integer,
    replace_empty_string,
    truncate_string,
    build_integer_processor,
    build_string_processor,
    build_subgroup_processor,
    MAX_CLASSROOM_TITLE_LENGTH,
)
from scrapy_app.items import LessonItem
from enums import Defaults


@pytest.mark.parametrize(
    "value, expectation",
    [
        ("12.03.2023 - Воскресение", does_not_raise()),
        ("   12.03.2023   -   Воскресение   ", does_not_raise()),
        ("12.03.2023 - Понедельник", does_not_raise()),  # День недели не совпадает
        ("12.03.2023", does_not_raise()),
        ("12-03-2023", does_not_raise()),
        (DateClass(2023, 3, 12), does_not_raise()),
        ("2023-12-03", does_not_raise()),  # Y-D-M
        ("Дата с лишним текстом 12.03.2023", does_not_raise()),  # Дата с лишним текстом

        ("2023-03-12", pytest.raises(AssertionError)),  # неверный порядок YMD
        ("Текст без даты", pytest.raises(ValueError)),
        ('', pytest.raises(ValueError)),
        (123, pytest.raises(TypeError)),
        (None, pytest.raises(TypeError)),
    ],
)
def test_parse_date(value, expectation):
    with expectation:
        parsed_date = parse_date(value)
        assert parsed_date == DateClass(2023, 3, 12)


@pytest.mark.parametrize(
    "value, min_value, max_value, result, expectation",
    [
        # Валидные кейсы
        (10, 0, 20, 10, does_not_raise()),  # В диапазоне
        (' 10 ', 0, 20, 10, does_not_raise()),  # В диапазоне, но строкой
        (0, 0, 20, 0, does_not_raise()),  # Равно минимальному
        (20, 0, 20, 20, does_not_raise()),  # Равно максимальному
        (5, float('-inf'), float('inf'), 5, does_not_raise()),

        # Невалидные кейсы
        (' ', 0, 20, 10, pytest.raises(ValueError)),  # Пустая строка
        (-1, 0, 20, None, pytest.raises(ValueError)),  # Меньше минимального
        (21, 0, 20, None, pytest.raises(ValueError)),  # Больше максимального
        (0, 3, 2, None, pytest.raises(ValueError))  # Некорректный диапазон
    ],
)
def test_validate_integer(value, min_value, max_value, result, expectation):
    with expectation:
        valid_value = validate_integer(value, min_value, max_value)
        assert valid_value == result


@pytest.mark.parametrize(
    "value, default, result",
    [
        ("", "default", "default"),  # Полностью пустая строка
        ("", None, None),  # Полностью пустая строка
        ("  ", "default", "default"),  # Строка с пробелами
        ("value", "default", "value"),  # Непустая строка
    ],
)
def test_replace_empty_string(value, default, result):
    processed_value = replace_empty_string(value, default)
    assert processed_value == result


@pytest.mark.parametrize(
    "value, max_length, result, expectation",
    [
        ("short", 10, "short", does_not_raise()),  # Не превышает длину
        ("very long string", 10, "very long ", does_not_raise()),  # Превышает длину
        ("exactly 10", 10, "exactly 10", does_not_raise()),  # Ровно длина
        ("", 10, "", does_not_raise()),  # Пустая строка

        ("", 0, "", pytest.raises(ValueError)),  # некорректная max_length
    ],
)
def test_truncate_string(value, max_length, result, expectation):
    with expectation:
        truncated_value = truncate_string(value, max_length)
        assert truncated_value == result


@pytest.mark.parametrize(
    "value, min_value, max_value, result, expectation",
    [
        (" 10 ", 0, 20, 10, does_not_raise()),  # В диапазоне, строкой
        (10, 0, 20, 10, does_not_raise()),  # В диапазоне

        ("", 0, 20, 0, pytest.raises(ValueError)),  # Пустая строка
        (" ", 0, 20, 0, pytest.raises(ValueError)),  # Строка с пробелами
        ("30", 0, 20, None, pytest.raises(ValueError)),  # Выше максимального
        ("5", 10, 20, None, pytest.raises(ValueError)), # Ниже минимального
        ("not an integer", 0, 20, None, pytest.raises(ValueError)),  # Некорректное значение
    ],
)
def test_integer_processor(value, min_value, max_value, result, expectation):
    processor = build_integer_processor(min_value, max_value)
    with expectation:
        processed_value = processor(value)[0]
        assert processed_value == result


@pytest.mark.parametrize(
    "value, default, min_value, max_value, result, expectation",
    [
        (" 10 ", None, 0, 20, 10, does_not_raise()),  # В диапазоне, строкой
        (10, None, 0, 20, 10, does_not_raise()),  # В диапазоне

        ("", 0, 0, 20, 0, does_not_raise()),  # Пустая строка
        ("  ", 0, 0, 20, 0, does_not_raise()),  # Строка с пробелами

        ("30", None, 0, 20, None, pytest.raises(ValueError)),  # Выше максимального
        ("5", None, 10, 20, None, pytest.raises(ValueError)), # Ниже минимального
        ("not an integer", None, 0, 20, None, pytest.raises(ValueError)),  # Некорректное значение
    ],
)
def test_subgroup_processor(value, default, min_value, max_value, result, expectation):
    processor = build_subgroup_processor(default, min_value, max_value)
    with expectation:
        processed_value = processor(value)[0]
        assert processed_value == result


@pytest.mark.parametrize(
    "value, default, max_length, result",
    [
        ("  Valid string  ", "default", 20, "Valid string"),  # Корректное значение
        ("", "default", 20, "default"),  # Значение по умолчанию
        ("Long string exceeding length", "default", 10, "Long strin"),  # Обрезка
        ("Long string exceeding length", "default", 10, "Long strin"),
    ],
)
def test_string_processor(value, default, max_length, result):
    processor = build_string_processor(default, max_length)
    processed_value = processor(value)[0]
    assert processed_value == result


@pytest.mark.parametrize(
    "raw_date_string, expectation, exception",
    [
        ("12.03.2023 - Воскресение", DateClass(2023, 3, 12), does_not_raise()),
        ("   12.03.2023   -   Воскресение   ", DateClass(2023, 3, 12), does_not_raise()),
        ("12.03.2023 - Понедельник", DateClass(2023, 3, 12), does_not_raise()),  # Даже если день недели не совпадает
        ("12.03.2023", DateClass(2023, 3, 12), does_not_raise()),
        ("12-03-2023", DateClass(2023, 3, 12), does_not_raise()),
        (DateClass(2023, 3, 12), DateClass(2023, 3, 12), does_not_raise()),

        ("2023-03-12", DateClass(2023, 3, 12), pytest.raises(AssertionError)),  # неверный порядок YMD
        ("Текст без даты", None, pytest.raises(ValueError)),
        ('', None, pytest.raises(ValueError)),
        (123, None,  pytest.raises(ValueError)),
        (None, None, pytest.raises(IndexError)),  # Процессоры пропускают None и не создает списка результатов
    ],
)
def test_date_processor(raw_date_string, expectation, exception):
    with exception:
        processed_date = LessonLoader().date_in(raw_date_string)[0]
        assert processed_date == expectation


@pytest.mark.parametrize(
    "field, input_value, expected_output, expectation",
    [
        ("date", " 12.03.2023 - Воскресение ", DateClass(2023, 3, 12), does_not_raise()),  # Валидное значение
        ("date", None, None, does_not_raise()),  # None пропускается без обработки (Особенность ItemLoader)
        ("date", "invalid", None, pytest.raises(ValueError)),  # Некорректное значение
        ("date", "  ", None, pytest.raises(ValueError)),  # Некорректное значение

        ("lesson_number", "  1 ", 1, does_not_raise()),  # Число строкой
        ("lesson_number", 1, 1, does_not_raise()), # int
        ("lesson_number", None, None, does_not_raise()), # None пропускается без обработки (Особенность ItemLoader)
        ("lesson_number", "  ", 1, pytest.raises(ValueError)),  # Пробелы
        ("lesson_number", "", 1, pytest.raises(ValueError)),  # Пустая строка
        ("lesson_number", "invalid", None, pytest.raises(ValueError)),  # Некорректное значение

        ("group_id", "  1 ", 1, does_not_raise()),  # Число строкой
        ("group_id", 1, 1, does_not_raise()),  # int
        ("group_id", None, None, does_not_raise()), # None пропускается без обработки (Особенность ItemLoader)
        ("group_id", "  ", 1, pytest.raises(ValueError)),  # Пробелы
        ("group_id", "", 1, pytest.raises(ValueError)),  # Пустая строка
        ("group_id", "invalid", None, pytest.raises(ValueError)),  # Некорректное значение

        ("subject_title", " Математика ", "Математика", does_not_raise()),  # Валидная строка
        ("subject_title", " ", Defaults.SUBJECT_TITLE, does_not_raise()),  # Замена на значение по умолчанию
        ("subject_title", None, None, does_not_raise()),  # None не обрабатывается

        ("teacher_fullname", " Иванов И.И. ", "Иванов И.И.", does_not_raise()),  # Валидная строка
        ("teacher_fullname", " ", Defaults.TEACHER_NAME, does_not_raise()),  # Замена на значение по умолчанию

        ("classroom_title", " А101 ", "А101", does_not_raise()),  # Валидная строка
        ("classroom_title", " ", Defaults.CLASSROOM, does_not_raise()),  # Замена на значение по умолчанию
        ("classroom_title", "Очень длинная строка", "Очень длинная строка"[:MAX_CLASSROOM_TITLE_LENGTH],
         does_not_raise()),  # Ожидаем обрезку строки

        ("subgroup", 1, 1, does_not_raise()), # int
        ("subgroup", " 1 ", 1, does_not_raise()),  # Число строкой
        ("subgroup", " ", Defaults.SUBGROUP, does_not_raise()), # Пробелы
        ("subgroup", "", Defaults.SUBGROUP, does_not_raise()), # Пустая строка
        ("subgroup", "invalid", 1, pytest.raises(ValueError)),  # Некорректная строка

    ],
)
def test_lesson_loader_single_field(field, input_value, expected_output, expectation):
    loader = LessonLoader(item=LessonItem())
    with expectation:
        loader.add_value(field, input_value)
        assert loader.get_output_value(field) == expected_output


def test_load_item_dict_structure():
    loader = LessonLoader(item=LessonItem())

    # Вводные данные для теста
    input_data = {
        "group_id": 1,
        "date": " 2025-01-01 ",
        "subject_title": " Математика ",
        "classroom_title": " 101 ",
        "teacher_fullname": " Иванов Иван Иванович ",
        "subgroup": " 1 ",
        "lesson_number": " 2 ",
    }

    # Ожидаемая структура
    expected_structure = {
        "group_id": 1,
        "period": {
            "lesson_number": 2,
            "date": "2025-01-01",
        },
        "subject": {
            "title": "Математика",
        },
        "classroom": {
            "title": "101",
        },
        "teacher": {
            "full_name": "Иванов Иван Иванович",
        },
        "subgroup": 1,
    }

    # Заполняем данные в загрузчик
    for field, value in input_data.items():
        loader.add_value(field, value)

    # Проверяем, что структура словаря совпадает
    assert loader.load_item_dict() == expected_structure
