import re
from bs4 import BeautifulSoup, Tag
from typing import List


class SchedulePageExtractor:
    DATE_ROW_LENGTH = 1
    LESSON_ROW_LENGTH = 5
    DATE_PATTERN = re.compile(r'\d{2}\.\d{2}\.\d{4}')

    def __init__(self, html):
        self.soup = BeautifulSoup(html, 'lxml')
        self.current_date = None
        self.previous_date = None
        self.previous_lesson_number = 0
        self.extracted_lessons = []

    def extract(self):
        for row in self.soup.find_all('tr', class_='shadow'):
            cells = row.find_all('td')
            if len(cells) == self.DATE_ROW_LENGTH:
                date_string = self._extract_date_row(cells)
                self.current_date = self._clean_date_sting(date_string)
            elif len(cells) == self.LESSON_ROW_LENGTH and self.current_date is not None:
                lesson_info = self._extract_lesson_row(cells)
                self._check_lessons_order(int(lesson_info['lesson_number']))
                lesson_info['date'] = self.current_date
                self.extracted_lessons.append(lesson_info)
            else:
                raise ValueError(f"Некорректная структура таблицы")

        return self.extracted_lessons

    @staticmethod
    def _extract_date_row(cells: List[Tag]) -> str:
        return cells[0].text

    @classmethod
    def _clean_date_sting(cls, raw_date_string: str) -> str:
        match = cls.DATE_PATTERN.search(raw_date_string)
        if match:
            return match.group()  # Возвращаем найденную строку даты
        raise ValueError(f"Не удалось извлечь дату из строки: {raw_date_string}")

    @staticmethod
    def _extract_lesson_row(cells: List[Tag]):
        return {
            'lesson_number': cells[0].text,
            'subject_title': cells[1].text,
            'classroom_title': cells[2].text,
            'teacher_fullname': cells[3].text,
            'subgroup': cells[4].text
        }

    def _check_lessons_order(self, lesson_number: int) -> None:
        """Проверяет порядок уроков и корректную смену дат"""
        if lesson_number <= self.previous_lesson_number and self.current_date == self.previous_date:
            raise ValueError("Неверный порядок уроков")
        self.previous_lesson_number = lesson_number
        self.previous_date = self.current_date
