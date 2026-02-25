from contextlib import nullcontext as does_not_raise
from datetime import date as DateClass, date

import pytest

from scrapy_app.item_loaders import (
    LessonLoader,
    parse_date,
    normalize_int,
    normalize_optional_int,
    normalize_html_text,
)
from scrapy_app.items import LessonItem


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
        (10, 0, 20, 10, does_not_raise()),
        (" 10 ", 0, 20, 10, does_not_raise()),
        (0, 0, 20, 0, does_not_raise()),
        (20, 0, 20, 20, does_not_raise()),

        (None, 0, 20, None, pytest.raises(ValueError)),
        ("", 0, 20, None, pytest.raises(ValueError)),
        (" ", 0, 20, None, pytest.raises(ValueError)),
        ("abc", 0, 20, None, pytest.raises(ValueError)),
        (21, 0, 20, None, pytest.raises(ValueError)),
        (-1, 0, 20, None, pytest.raises(ValueError)),
    ],
)
def test_normalize_int(value, min_value, max_value, result, expectation):
    with expectation:
        assert normalize_int(value, min_value, max_value) == result


@pytest.mark.parametrize(
    "value, min_value, max_value, result, expectation",
    [
        (None, 0, 9, None, does_not_raise()),
        ("", 0, 9, None, does_not_raise()),
        (" ", 0, 9, None, does_not_raise()),

        ("1", 0, 9, 1, does_not_raise()),
        (1, 0, 9, 1, does_not_raise()),

        ("abc", 0, 9, None, pytest.raises(ValueError)),
        ("10", 0, 9, None, pytest.raises(ValueError)),
    ],
)
def test_normalize_optional_int(value, min_value, max_value, result, expectation):
    with expectation:
        assert normalize_optional_int(value, min_value, max_value) == result


@pytest.mark.parametrize(
    "value, result, expectation",
    [
        (" Математика ", "Математика", does_not_raise()),
        ("", None, does_not_raise()),
        ("   ", None, does_not_raise()),
        (None, None, does_not_raise()),
        (123, "123", does_not_raise()),

    ],
)
def test_normalize_html_text(value, result, expectation):
    with expectation:
        assert normalize_html_text(value) == result


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
        # date
        ("date", " 12.03.2023 - Воскресение ", DateClass(2023, 3, 12), does_not_raise()),  # Валидное значение
        ("date", None, None, does_not_raise()),  # None пропускается без обработки (Особенность ItemLoader)
        ("date", "invalid", None, pytest.raises(ValueError)),  # Некорректное значение
        ("date", "  ", None, pytest.raises(ValueError)),  # Некорректное значение

        # lesson_number (обязательное число)
        ("lesson_number", "  1 ", 1, does_not_raise()),  # Число строкой
        ("lesson_number", 1, 1, does_not_raise()), # int
        ("lesson_number", None, None, does_not_raise()), # None пропускается без обработки (Особенность ItemLoader)
        ("lesson_number", "  ", 1, pytest.raises(ValueError)),  # Пробелы
        ("lesson_number", "", 1, pytest.raises(ValueError)),  # Пустая строка
        ("lesson_number", "abc", None, pytest.raises(ValueError)),  # Некорректное значение

        # group_id
        ("group_id", "  1 ", 1, does_not_raise()),  # Число строкой
        ("group_id", 1, 1, does_not_raise()),  # int
        ("group_id", None, None, does_not_raise()), # None пропускается без обработки (Особенность ItemLoader)

        ("group_id", "-1", -1, pytest.raises(ValueError)), # Отрицательное
        ("group_id", "  ", 1, pytest.raises(ValueError)),  # Пробелы
        ("group_id", "", 1, pytest.raises(ValueError)),  # Пустая строка
        ("group_id", "invalid", None, pytest.raises(ValueError)),  # Некорректное значение

        ("subject_title", " Математика ", "Математика", does_not_raise()),  # Валидная строка
        ("subject_title", " ", None, does_not_raise()),  # Замена на значение по умолчанию
        ("subject_title", None, None, does_not_raise()),  # None не обрабатывается

        ("teacher_fullname", " Иванов И.И. ", "Иванов И.И.", does_not_raise()),  # Валидная строка
        ("teacher_fullname", " ", None, does_not_raise()),  # Замена на значение по умолчанию

        ("classroom_title", " А101 ", "А101", does_not_raise()),  # Валидная строка
        ("classroom_title", " ", None, does_not_raise()),  # Замена на значение по умолчанию

        ("subgroup", 1, 1, does_not_raise()), # int
        ("subgroup", " 1 ", 1, does_not_raise()),  # Число строкой
        ("subgroup", " ", None, does_not_raise()), # Пробелы
        ("subgroup", "", None, does_not_raise()), # Пустая строка
        ("subgroup", "invalid", 1, pytest.raises(ValueError)),  # Некорректная строка

    ],
)
def test_lesson_loader_single_field(field, input_value, expected_output, expectation):
    loader = LessonLoader(item=LessonItem())
    with expectation:
        loader.add_value(field, input_value)
        assert loader.get_output_value(field) == expected_output



@pytest.mark.parametrize(
    "input_data, expected_structure",
    [
        # Полностью заполненный урок
        ({
            "group_id": 1,
            "date": " 2025-01-01 ",
            "subject_title": " Математика ",
            "classroom_title": " 101 ",
            "teacher_fullname": " Иванов Иван Иванович ",
            "subgroup": " 1 ",
            "lesson_number": " 2 ",
        },
        {
            "group_id": 1,
            "period": {
                "lesson_number": 2,
                "date": date.fromisoformat("2025-01-01"),
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
        }),

        # Урок с допустимыми пропусками
        ({
            "group_id": "1",
            "date": " 2025-01-01 ",
            "subject_title": " ",
            "classroom_title": "",
            "teacher_fullname": " ",
            "subgroup": "",
            "lesson_number": " 2 ",
        },
        {
            "group_id": 1,
            "period": {
                "lesson_number": 2,
                "date": date.fromisoformat("2025-01-01"),
            },
            "subject": {
                "title": None,
            },
            "classroom": {
                "title": None,
            },
            "teacher": {
                "full_name": None,
            },
            "subgroup": None,
        }),

    ],
)
def test_load_item_dict_structure(input_data, expected_structure):
    loader = LessonLoader(item=LessonItem())

    # Заполняем данные в загрузчик
    for field, value in input_data.items():
        loader.add_value(field, value)

    # Проверяем, что структура словаря совпадает
    assert loader.load_item_dict() == expected_structure
