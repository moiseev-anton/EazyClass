from datetime import date
import pytest
from contextlib import nullcontext as does_not_raise
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
    @pytest.mark.parametrize('case, expectation', [
        # Валидные данные
        ({"lesson_number": 1, "subject_title": '', "classroom_title": '', "teacher_fullname": '', "subgroup": ''},
         does_not_raise()),
        # Невалидные данные
        ({"lesson_number": 1, "date": ''}, pytest.raises(ValidationError)),
        ({"lesson_number": 1, "group_id": ''}, pytest.raises(ValidationError)),
    ])
    def test_empty_strings(self, case, expectation):
        """Проверка обработки пустых строк и невалидных случаев"""
        with expectation:
            lesson_parser = LessonParser(**case)
            assert lesson_parser.subject_title == SUBJECT_DEFAULT_VALUE
            assert lesson_parser.classroom_title == CLASSROOM_DEFAULT_VALUE
            assert lesson_parser.teacher_fullname == TEACHER_DEFAULT_VALUE
            assert lesson_parser.subgroup == SUBGROUP_DEFAULT_VALUE

    @pytest.mark.parametrize('case, expectation', [
        # Валидные значения
        ({"lesson_number": 5}, does_not_raise()),
        ({"lesson_number": '5'}, does_not_raise()),

        # Невалидные значения
        ({"lesson_number": 0}, pytest.raises(ValidationError)),
        ({"lesson_number": 10}, pytest.raises(ValidationError)),
        ({"lesson_number": '-5'}, pytest.raises(ValidationError)),
        ({"lesson_number": '11'}, pytest.raises(ValidationError)),
        ({"lesson_number": None}, pytest.raises(ValidationError)),
        ({}, pytest.raises(ValidationError)),
    ])
    def test_lesson_number(self, case, expectation):
        """Проверка на правильную обработку значений lesson_number"""
        with expectation:
            lesson_parser = LessonParser(**case)
            assert lesson_parser.lesson_number == int(case['lesson_number'])

    @pytest.mark.parametrize('case, expectation', [
        # Валидные значения
        ({"lesson_number": 5, "subgroup": 0}, does_not_raise()),
        ({"lesson_number": 5, "subgroup": 5}, does_not_raise()),
        ({"lesson_number": 5, "subgroup": '3'}, does_not_raise()),

        # Невалидные значения
        ({"lesson_number": 5, "subgroup": -1}, pytest.raises(ValidationError)),
        ({"lesson_number": 5, "subgroup": 10}, pytest.raises(ValidationError)),
        ({"lesson_number": 5, "subgroup": '-5'}, pytest.raises(ValidationError)),
        ({"lesson_number": 5, "subgroup": '15'}, pytest.raises(ValidationError)),
        ({"lesson_number": 5, "subgroup": None}, pytest.raises(ValidationError)),
        ({"lesson_number": 5, "subgroup": 'abc'}, pytest.raises(ValidationError)),
    ])
    def test_subgroup(self, case, expectation):
        """Проверка валидации значения subgroup."""
        with expectation:
            lesson_parser = LessonParser(**case)
            assert lesson_parser.subgroup == int(case['subgroup'])

    @pytest.mark.parametrize('case, expectation', [
        # Валидные значения
        ({"lesson_number": 5, "date": date(2024, 12, 6)}, does_not_raise()),  # объект date
        ({"lesson_number": 5, "date": '06.12.2024'}, does_not_raise()),  # строка в формате dd.mm.yyyy
        ({"lesson_number": 5, "date": '2024-12-06'}, does_not_raise()),  # строка в формате yyyy-mm-dd

        # Невалидные значения
        ({"lesson_number": 1, "date": '06/12/2024'}, pytest.raises(ValidationError)),  # неверный формат
        ({"lesson_number": 1, "date": '2024-13-06'}, pytest.raises(ValidationError)),  # неверный формат
        ({"lesson_number": 1, "date": ''}, pytest.raises(ValidationError)),  # пустая строка
        ({"lesson_number": 1, "date": None}, pytest.raises(ValidationError)),
    ])
    def test_date(self, case, expectation):
        """Проверка на корректную обработку даты"""
        with expectation:
            lesson_parser = LessonParser(**case)
            assert lesson_parser.date == date(2024, 12, 6)

    @pytest.mark.parametrize('case, expectation', [
        # Валидные значения
        ({"lesson_number": 5, "group_id": 101}, does_not_raise()),
        ({"lesson_number": 5, "group_id": '101'}, does_not_raise()),

        # Невалидные значения
        ({"lesson_number": 5, "group_id": -1}, pytest.raises(ValidationError)),
        ({"lesson_number": 5, "group_id": ''}, pytest.raises(ValidationError)),
    ])
    def test_group_id(self, case, expectation):
        """Проверка на корректную обработку даты"""
        with expectation:
            lesson_parser = LessonParser(**case)
            assert lesson_parser.group_id == int(case['group_id'])

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
