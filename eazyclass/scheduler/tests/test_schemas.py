from datetime import date
import pytest
from pydantic import ValidationError
from scheduler.schemas import (LessonParser,
                               MAX_SUBJECT_TITLE_LENGTH,
                               MAX_CLASSROOM_TITLE_LENGTH,
                               MAX_TEACHER_FULLNAME_LENGTH,
                               SUBJECT_DEFAULT_VALUE,
                               TEACHER_DEFAULT_VALUE,
                               CLASSROOM_DEFAULT_VALUE,
                               SUBGROUP_DEFAULT_VALUE)


class TestLessonParse:

    def test_absent_optional_fields(self):
        """Проверка корректной обработки отсутствующих необязательных полей"""
        data = {"lesson_number": 1}  # обязательное поле

        lesson_parser = LessonParser(**data)

        # Поля, которые не переданы, должны принимать значения по умолчанию
        assert lesson_parser.subject_title == SUBJECT_DEFAULT_VALUE
        assert lesson_parser.classroom_title == CLASSROOM_DEFAULT_VALUE
        assert lesson_parser.teacher_fullname == TEACHER_DEFAULT_VALUE
        assert lesson_parser.subgroup == SUBGROUP_DEFAULT_VALUE
        assert lesson_parser.date is None
        assert lesson_parser.group_id is None

    def test_valid_empty_strings(self):
        """Проверка обработки пустых строк"""
        valid_data = {'lesson_number': 1,  # обязательное поле
                      'subject_title': '',
                      'classroom_title': '',
                      'teacher_fullname': '',
                      'subgroup': ''
                      }

        lesson_parser = LessonParser(**valid_data)

        assert lesson_parser.subject_title == SUBJECT_DEFAULT_VALUE
        assert lesson_parser.classroom_title == CLASSROOM_DEFAULT_VALUE
        assert lesson_parser.teacher_fullname == TEACHER_DEFAULT_VALUE
        assert lesson_parser.subgroup == SUBGROUP_DEFAULT_VALUE

    @pytest.mark.parametrize('case', [
        {'lesson_number': 1, 'date': ''},
        {'lesson_number': 1, 'group_id': ''}
    ])
    def test_invalid_empty_strings(self, case):
        with pytest.raises(ValidationError):
            LessonParser(**case)

    @pytest.mark.parametrize('case', [
        {"lesson_number": 5},  # Число в пределах допустимого диапазона
        {"lesson_number": '5'} # Строка, которая будет приведена к числу
    ])
    def test_lesson_number_validation(self, case):
        """Проверка на правильную обработку значений lesson_number"""
        lesson_parser = LessonParser(**case)
        assert lesson_parser.lesson_number == int(case['lesson_number'])

    @pytest.mark.parametrize('case', [
        {"lesson_number": 0},
        {"lesson_number": 10},
        {"lesson_number": '-5'},
        {"lesson_number": '11'},
        {"lesson_number": None},
        {},
    ])
    def test_lesson_number_validation(self, case):
        """Проверка на правильную обработку значений lesson_number"""
        with pytest.raises(ValidationError):
            LessonParser(**case)

    def test_strip_whitespace(self):
        valid_data = {'lesson_number': ' 1  ',  # обязательное поле
                      'subject_title': ' Математика  ',
                      'classroom_title': '  А101  ',
                      'teacher_fullname': ' Иванов Иван Иванови  ',
                      'subgroup': ' 1 ',
                      'date': '  2024-12-06 ',
                      'group_id': ' 1 '
                      }

        lesson_parser = LessonParser(**valid_data)

        assert lesson_parser.lesson_number == 1
        assert lesson_parser.subject_title == 'Математика'
        assert lesson_parser.classroom_title == 'А101'
        assert lesson_parser.teacher_fullname == 'Иванов Иван Иванови'
        assert lesson_parser.subgroup == 1
        assert lesson_parser.date == date(2024, 12, 6)
        assert lesson_parser.group_id == 1

    def test_truncate(self):
        """Проверка обрезки строк"""
        data = {"lesson_number": 5,
                "subject_title": 'И' * (MAX_SUBJECT_TITLE_LENGTH + 1),
                "classroom_title": 'А' * (MAX_CLASSROOM_TITLE_LENGTH + 1),
                "teacher_fullname": 'И' * (MAX_TEACHER_FULLNAME_LENGTH + 1)
                }

        lesson_parser = LessonParser(**data)
        assert len(lesson_parser.subject_title) == MAX_SUBJECT_TITLE_LENGTH
        assert len(lesson_parser.classroom_title) == MAX_CLASSROOM_TITLE_LENGTH
        assert len(lesson_parser.teacher_fullname) == MAX_TEACHER_FULLNAME_LENGTH

    @pytest.mark.parametrize('case', [
        {"lesson_number": 5, "subgroup": 0},
        {"lesson_number": 5, "subgroup": 5},
        {"lesson_number": 5, "subgroup": '3'},
    ])
    def test_valid_subgroup(self, case):
        """Проверка на различные значения для subgroup"""
        lesson_parser = LessonParser(**case)
        assert lesson_parser.subgroup == int(case['subgroup'])

    @pytest.mark.parametrize('case', [
        {"lesson_number": 5, "subgroup": -1},
        {"lesson_number": 5, "subgroup": 10},
        {"lesson_number": 5, "subgroup": '-5'},
        {"lesson_number": 5, "subgroup": '15'},
        {"lesson_number": 5, "subgroup": None},
        {"lesson_number": 5, "subgroup": 'abc'},
    ])
    def test_invalid_subgroup(self, case):
        with pytest.raises(ValidationError):
            LessonParser(**case)

    @pytest.mark.parametrize('case', [
        {"lesson_number": 5, "date": date(2024, 12, 6)},  # объект date
        {"lesson_number": 5, "date": '06.12.2024'},  # строка в формате dd.mm.yyyy
        {"lesson_number": 5, "date": '2024-12-06'},  # строка в формате yyyy-mm-dd
    ])
    def test_valide_date(self, case):
        """Проверка на корректную обработку даты"""
        lesson_parser = LessonParser(**case)
        assert lesson_parser.date == date(2024, 12, 6)

    @pytest.mark.parametrize('case', [
        {"lesson_number": 1, "date": '06/12/2024'},  # неверный формат
        {"lesson_number": 1, "date": '2024-13-06'},  # неверный формат
        {"lesson_number": 1, "date": ''},  # пустая строка
        {"lesson_number": 1, "date": None},
    ])
    def test_invalide_date(self, case):
        with pytest.raises(ValidationError):
            LessonParser(**case)

    @pytest.mark.parametrize('case', [
        {"lesson_number": 5, "group_id": 101},
        {"lesson_number": 5, "group_id": '101'}
    ])
    def test_valide_group_id(self, case):
        """Проверка на корректную обработку даты"""
        lesson_parser = LessonParser(**case)
        assert lesson_parser.group_id == int(case['group_id'])

    @pytest.mark.parametrize('case', [
        {"lesson_number": 5, "group_id": -1},
        {"lesson_number": 5, "group_id": ''},
    ])
    def test_invalide_group_id(self, case):
        with pytest.raises(ValidationError):
            LessonParser(**case)

