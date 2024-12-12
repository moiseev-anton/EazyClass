from contextlib import nullcontext as does_not_raise

import bs4
import pytest

from scheduler.scapper.extractor import SchedulePageExtractor
from scheduler.tests.html_test_cases import html_test_cases


@pytest.mark.parametrize("case, expected_result, expectation",
                         html_test_cases,
                         ids=[f"html_case-{i}" for i in range(len(html_test_cases))])
def test_extract_valid_html(case, expected_result, expectation):
    with expectation:
        result = SchedulePageExtractor(case).extract()
        assert result == expected_result


class TestSchedulePageExtractor:

    @pytest.fixture(autouse=True)
    def setup(self):
        """Фикстура для создания экземпляра SchedulePageExtractor."""
        self.extractor = SchedulePageExtractor("<html></html>")

    @pytest.mark.parametrize("case, expectation", [
        # Валидные данные
        ('07.12.2024 - Суббота', does_not_raise()),
        ('07.12.2024', does_not_raise()),
        ('  07.12.2024!  ', does_not_raise()),
        ('[07.12.2024]', does_not_raise()),
        ('Дата:07.12.2024г.', does_not_raise()),

        # Невалидные данные
        ('', pytest.raises(ValueError)),
        ('  ', pytest.raises(ValueError)),
        ('Не содержит дату', pytest.raises(ValueError)),
        ('Неверный формат 2024-12-07', pytest.raises(ValueError)),
        ('Неверный формат 07-12-2024', pytest.raises(ValueError)),
        ('Неверный формат 7.2.2024', pytest.raises(ValueError)),
    ])
    def test_clean_date_sting_valid(self, case, expectation):
        with expectation:
            result = self.extractor._clean_date_sting(case)
            assert result == '07.12.2024'

    @pytest.mark.parametrize(
        "previous_date, current_date, previous_lesson_number, lesson_number, expectation",
        [
            # Валидные данные
            ("06.12.2024", "06.12.2024", 2, 3, does_not_raise()),
            ("06.12.2024", "07.12.2024", 2, 1, does_not_raise()),
            ("06.12.2024", "07.12.2024", 2, 2, does_not_raise()),

            # Невалидные данные
            ("06.12.2024", "06.12.2024", 2, 1, pytest.raises(ValueError)),
            ("06.12.2024", "06.12.2024", 2, 2, pytest.raises(ValueError)),

        ]
    )
    def test_check_lessons_order_valid(self, previous_date, previous_lesson_number, current_date, lesson_number,
                                       expectation):
        self.extractor.previous_date = previous_date
        self.extractor.previous_lesson_number = previous_lesson_number
        self.extractor.current_date = current_date

        with expectation:
            self.extractor._check_lessons_order(lesson_number)
            assert self.extractor.previous_lesson_number == lesson_number
            assert self.extractor.previous_date == current_date

    def test_extract_date_row(self, mocker):
        valid_cells = [mocker.Mock(text='Текст')]
        result = self.extractor._extract_date_row(valid_cells)
        assert result == "Текст"

        cells = [bs4.Tag(name='td')] # тег bs4 не содержащий текст должен вернуть пустую строку
        result = self.extractor._extract_date_row(cells)
        assert result == ""

        empty_cells = []
        with pytest.raises(IndexError):
            self.extractor._extract_date_row(empty_cells)

    def test_extract_lesson_row_valid(self, mocker):
        cells = [
            mocker.Mock(text="1"),  # lesson_number
            mocker.Mock(text=" Математика"),  # subject_title
            mocker.Mock(text="Ауд. 101 "),  # classroom_title
            mocker.Mock(text="Иванов И.И."),  # teacher_fullname
            mocker.Mock(text="1"),  # subgroup
        ]
        expected_result = {
            'lesson_number': "1",
            'subject_title': " Математика",
            'classroom_title': "Ауд. 101 ",
            'teacher_fullname': "Иванов И.И.",
            'subgroup': "1",
        }

        result = self.extractor._extract_lesson_row(cells)
        assert result == expected_result

    def test_extract_lesson_row_invalid(self, mocker):
        cases = [
            [mocker.Mock(text="1")],
            []
        ]

        for case in cases:
            with pytest.raises(IndexError):
                self.extractor._extract_lesson_row(case)
