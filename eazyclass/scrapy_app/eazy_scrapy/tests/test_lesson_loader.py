from contextlib import nullcontext as does_not_raise

import pytest

from scrapy_app.eazy_scrapy.item_loaders import *


class TestLessonLoader:
    @pytest.mark.parametrize(
        "value, min_value, max_value, result, expectation",
        [
            # Валидные кейсы
            (10, 0, 20, 10, does_not_raise()),  # В диапазоне
            (0, 0, 20, 0, does_not_raise()),  # Равно минимальному
            (20, 0, 20, 20, does_not_raise()),  # Равно максимальному
            (5, 5, 5, 5, does_not_raise()),

            # Невалидные кейсы
            (-1, 0, 20, None, pytest.raises(ValueError)),  # Меньше минимального
            (21, 0, 20, None, pytest.raises(ValueError)),  # Больше максимального
            (0, 3, 2, None, pytest.raises(ValueError))
        ],
    )
    def test_validate_integer(self, value, min_value, max_value, result, expectation):
        with expectation:
            valid_value = validate_integer(value, min_value, max_value)
            assert valid_value == result

    @pytest.mark.parametrize(
        "value, default, result, expectation",
        [
            ("  ", "default", "default", does_not_raise()),  # Пустая строка
            ("value", "default", "value", does_not_raise()),  # Непустая строка
            ("", "default", "default", does_not_raise()),  # Полностью пустая строка
            ("", None, None, does_not_raise()),  # Полностью пустая строка

        ],
    )
    def test_replace_empty_string(self, value, default, result, expectation):
        with expectation:
            processed_value = replace_empty_string(value, default)
            assert processed_value == result

    @pytest.mark.parametrize(
        "value, max_length, result, expectation",
        [
            ("short", 10, "short", does_not_raise()),  # Не превышает длину
            ("very long string", 10, "very long ", does_not_raise()),  # Превышает длину
            ("exactly 10!", 10, "exactly 10", does_not_raise()),  # Ровно длина
            ("", 10, "", does_not_raise()),  # Пустая строка

            ("", 0, "", pytest.raises(ValueError))
        ],
    )
    def test_truncate_string(self, value, max_length, result, expectation):
        with expectation:
            truncated_value = truncate_string(value, max_length)
            assert truncated_value == result

    @pytest.mark.parametrize(
        "raw_date_string, result, expectation",
        [
            ("Some text 12.03.2023", "12.03.2023", does_not_raise()),
            ("Another format 2023-03-12", None, pytest.raises(ValueError)),
            ("No date here", None, pytest.raises(ValueError)),
            ("", None, pytest.raises(ValueError)),
        ],
    )
    def test_date_extract(self, raw_date_string, result, expectation):
        with expectation:
            extracted_date = date_extract(raw_date_string)
            assert extracted_date == result

    @pytest.mark.parametrize(
        "value, expectation",
        [
            ("12.03.2023", does_not_raise()),
            ("2023-03-12", does_not_raise()),
            (date(2023, 3, 12), does_not_raise()),
            ("invalid-date", pytest.raises(ValueError)),
            ('', pytest.raises(ValueError)),
            (123, pytest.raises(TypeError)),
            (None, pytest.raises(TypeError)),
        ],
    )
    def test_parse_date(self, value, expectation):
        with expectation:
            parsed_date = parse_date(value)
            assert parsed_date == date(2023, 3, 12)

    @pytest.mark.parametrize(
        "value, default, min_value, max_value, result, expectation",
        [
            (" 10 ", None, 0, 20, 10, does_not_raise()),  # В диапазоне
            ("", 0, 0, 20, 0, does_not_raise()),  # Значение по умолчанию

            ("30", None, 0, 20, None, pytest.raises(ValueError)),  # Выше максимального
            ("5", None, 10, 20, None, pytest.raises(ValueError)),
            ("not an integer", None, 0, 20, None, pytest.raises(ValueError)),  # Некорректное значение
        ],
    )
    def test_integer_processor(self, value, default, min_value, max_value, result, expectation):
        processor = build_integer_processor(default, min_value, max_value)
        with expectation:
            processed_value = processor(value)[0]
            assert processed_value == result

    @pytest.mark.parametrize(
        "value, default, max_length, result, expectation",
        [
            ("  Valid string  ", "default", 20, "Valid string", does_not_raise()),  # Корректное значение
            ("", "default", 20, "default", does_not_raise()),  # Значение по умолчанию
            ("Long string exceeding length", "default", 10, "Long strin", does_not_raise()),  # Обрезка
            ("Long string exceeding length", "default", 10, "Long strin", does_not_raise()),
        ],
    )
    def test_string_processor(self, value, default, max_length, result, expectation):
        processor = build_string_processor(default, max_length)
        with expectation:
            processed_value = processor(value)[0]
            assert processed_value == result

    @pytest.mark.parametrize(
        "raw_date_string, expectation",
        [
            ("12.03.2023", does_not_raise()),
            ("Некоторый 12.03.2023  текст", does_not_raise()),
            ("Другой формат 2023-03-12", pytest.raises(ValueError)),
            ("Без даты", pytest.raises(ValueError)),
            ("", pytest.raises(ValueError)),
        ],
    )
    def test_date_processor(self, raw_date_string, expectation):
        with expectation:
            processed_date = LessonLoader().date_in(raw_date_string)[0]
            assert processed_date == date(2023, 3, 12)
