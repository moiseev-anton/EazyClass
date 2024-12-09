import pytest
from bs4 import Tag

from scheduler.parsers.shedule_page_data_extractor import SchedulePageExtractor
from scheduler.tests.html_test_cases import html_test_cases, invalid_html_test_cases


@pytest.mark.parametrize("html, expected_result", html_test_cases)
def test_extract_valid_html(html, expected_result):
    result = SchedulePageExtractor(html).extract()
    assert result == expected_result


@pytest.mark.parametrize("html", invalid_html_test_cases)
def test_extract_invalid(html):
    extractor = SchedulePageExtractor(html)
    with pytest.raises(ValueError):
        extractor.extract()


class TestSchedulePageExtractorMethods:
    @pytest.fixture(autouse=True)
    def setup(self):
        """Фикстура для создания экземпляра SchedulePageExtractor."""
        self.extractor = SchedulePageExtractor("<html></html>")

    @pytest.mark.parametrize("case", [
        '07.12.2024 - Суббота',
        '07.12.2024',
        '  07.12.2024!  ',
        '[07.12.2024]',
        'Дата:07.12.2024г.',
    ])
    def test_clean_date_sting_valid(self, case):
        result = self.extractor._clean_date_sting(case)
        assert result == '07.12.2024'

    @pytest.mark.parametrize("case", [
        '',
        '  ',
        'Не содержит дату',
        'Неверный формат 2024-12-07',
        'Неверный формат 07-12-2024',
        'Неверный формат 7.2.2024',
    ])
    def test_clean_date_sting_invalid(self, case):
        with pytest.raises(ValueError):
            self.extractor._clean_date_sting(case)

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

    @pytest.mark.parametrize(
        "previous_date, current_date, previous_lesson_number, lesson_number",
        [
            ("06.12.2024", "06.12.2024", 2, 3),
            ("06.12.2024", "07.12.2024", 2, 1),
            ("06.12.2024", "07.12.2024", 2, 2),
        ]
    )
    def test_check_lessons_order_valid(self, previous_date, previous_lesson_number, current_date, lesson_number):
        self.extractor.previous_date = previous_date
        self.extractor.previous_lesson_number = previous_lesson_number
        self.extractor.current_date = current_date

        self.extractor._check_lessons_order(lesson_number)
        assert self.extractor.previous_lesson_number == lesson_number
        assert self.extractor.previous_date == current_date

    @pytest.mark.parametrize(
        "previous_date, current_date, previous_lesson_number, lesson_number",
        [
            ("06.12.2024", "06.12.2024", 2, 1),
            ("06.12.2024", "06.12.2024", 2, 2),
        ]
    )
    def test_check_lessons_order_invalid(self, previous_date, previous_lesson_number, current_date, lesson_number):
        self.extractor.previous_date = previous_date
        self.extractor.previous_lesson_number = previous_lesson_number
        self.extractor.current_date = current_date

        with pytest.raises(ValueError):
            self.extractor._check_lessons_order(lesson_number)

    def test_extract_date_row(self, mocker):
        valid_cells = [mocker.Mock(text='Текст')]
        result = self.extractor._extract_date_row(valid_cells)
        assert result == "Текст"

        cells = [Tag(name='td')]
        result = self.extractor._extract_date_row(cells)
        assert result == ""

        empty_cells = []
        with pytest.raises(IndexError):
            self.extractor._extract_date_row(empty_cells)
