from datetime import date
from django.test import TestCase
from pydantic import ValidationError
from scheduler.schemas import (LessonParser,
                               MAX_SUBJECT_TITLE_LENGTH,
                               MAX_CLASSROOM_TITLE_LENGTH,
                               MAX_TEACHER_FULLNAME_LENGTH,
                               SUBJECT_DEFAULT_VALUE,
                               TEACHER_DEFAULT_VALUE,
                               CLASSROOM_DEFAULT_VALUE,
                               SUBGROUP_DEFAULT_VALUE)


class TestLessonParser(TestCase):

    def test_absent_optional_fields(self):
        """
        Проверка корректной обработки отсутствующих необязательных полей.
        """
        data = {"lesson_number": 1}  # обязательное поле

        lesson_parser = LessonParser(**data)

        # Поля, которые не переданы, должны принимать значения по умолчанию
        self.assertEqual(lesson_parser.subject_title, SUBJECT_DEFAULT_VALUE)
        self.assertEqual(lesson_parser.classroom_title, CLASSROOM_DEFAULT_VALUE)
        self.assertEqual(lesson_parser.teacher_fullname, TEACHER_DEFAULT_VALUE)
        self.assertEqual(lesson_parser.subgroup, SUBGROUP_DEFAULT_VALUE)
        self.assertIsNone(lesson_parser.date)
        self.assertIsNone(lesson_parser.group_id)

    def test_turning_empty_strings_to_default(self):
        """Проверка обработки пустых строк"""
        valid_data = {'lesson_number': 1,  # обязательное поле
                      'subject_title': '',
                      'classroom_title': '',
                      'teacher_fullname': '',
                      'subgroup': ''
                      }

        lesson_parser = LessonParser(**valid_data)

        self.assertEqual(lesson_parser.subject_title, SUBJECT_DEFAULT_VALUE)
        self.assertEqual(lesson_parser.classroom_title, CLASSROOM_DEFAULT_VALUE)
        self.assertEqual(lesson_parser.teacher_fullname, TEACHER_DEFAULT_VALUE)
        self.assertEqual(lesson_parser.subgroup, SUBGROUP_DEFAULT_VALUE)

        invalid_data = [
            {'lesson_number': 1, 'date': ''},
            {'lesson_number': 1, 'group_id': ''}
        ]

        for data in invalid_data:
            with self.assertRaises(ValidationError):
                LessonParser(**data)

    def test_lesson_number_validation(self):
        """Проверка на правильную обработку значений lesson_number"""
        valid_data = [
            {"lesson_number": 5},  # Число в пределах допустимого диапазона
            {"lesson_number": '5'},  # Строка, которая будет приведена к числу
        ]

        for data in valid_data:
            lesson_parser = LessonParser(**data)
            self.assertEqual(lesson_parser.lesson_number, 5)

        # Проверка на ошибку при значении меньше 1 или больше 9
        invalid_data = [
            {"lesson_number": 0},
            {"lesson_number": 10},
            {"lesson_number": '-5'},
            {"lesson_number": '11'},
            {"lesson_number": None}
        ]

        for data in invalid_data:
            with self.assertRaises(ValidationError):
                LessonParser(**data)

        # Проверка на обязательность поля (если не передано — ошибка)
        with self.assertRaises(ValidationError):
            LessonParser(**{})

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

        self.assertEqual(lesson_parser.lesson_number, 1)
        self.assertEqual(lesson_parser.subject_title, 'Математика')
        self.assertEqual(lesson_parser.classroom_title, 'А101')
        self.assertEqual(lesson_parser.teacher_fullname, 'Иванов Иван Иванови')
        self.assertEqual(lesson_parser.subgroup, 1)
        self.assertEqual(lesson_parser.date, date(2024, 12, 6))
        self.assertEqual(lesson_parser.group_id, 1)

    def test_truncate(self):
        """Проверка обрезки строк"""
        data = {"lesson_number": 5,
                "subject_title": 'И' * (MAX_SUBJECT_TITLE_LENGTH + 1),
                "classroom_title": 'А' * (MAX_CLASSROOM_TITLE_LENGTH + 1),
                "teacher_fullname": 'И' * (MAX_TEACHER_FULLNAME_LENGTH + 1)
                }

        lesson_parser = LessonParser(**data)
        self.assertLessEqual(len(lesson_parser.subject_title), MAX_SUBJECT_TITLE_LENGTH)
        self.assertLessEqual(len(lesson_parser.classroom_title), MAX_CLASSROOM_TITLE_LENGTH)
        self.assertLessEqual(len(lesson_parser.teacher_fullname), MAX_TEACHER_FULLNAME_LENGTH)

    def test_subgroup_validation(self):
        """Проверка на различные значения для subgroup"""
        valid_data = [
            {"lesson_number": 5, "subgroup": 0},
            {"lesson_number": 5, "subgroup": 5},
            {"lesson_number": 5, "subgroup": '3'},  # Строка, которая будет приведена к числу
        ]

        for data in valid_data:
            lesson_parser = LessonParser(**data)
            self.assertEqual(lesson_parser.subgroup, int(data['subgroup']))

        # Проверка на ошибку для значений за пределами диапазона
        invalid_data = [
            {"lesson_number": 5, "subgroup": -1},
            {"lesson_number": 5, "subgroup": 10},
            {"lesson_number": 5, "subgroup": '-5'},
            {"lesson_number": 5, "subgroup": '15'},
            {"lesson_number": 5, "subgroup": None},
            {"lesson_number": 5, "subgroup": 'abc'},
        ]

        for data in invalid_data:
            with self.assertRaises(ValidationError):
                LessonParser(**data)

    def test_date_validation(self):
        """Проверка на корректную обработку даты"""
        valid_data = [
            {"lesson_number": 5, "date": date(2024, 12, 6)},  # объект date
            {"lesson_number": 5, "date": '06.12.2024'},  # строка в формате dd.mm.yyyy
            {"lesson_number": 5, "date": '2024-12-06'},  # строка в формате yyyy-mm-dd
        ]

        for data in valid_data:
            lesson_parser = LessonParser(**data)
            self.assertEqual(lesson_parser.date, date(2024, 12, 6))

        # Проверка на некорректные форматы
        invalid_data = [
            {"lesson_number": 1, "date": '06/12/2024'},  # неверный формат
            {"lesson_number": 1, "date": '2024-13-06'},  # неверный формат
            {"lesson_number": 1, "date": ''},  # пустая строка, должна привести к ошибке
            {"lesson_number": 1, "date": None},  # пустая строка, должна привести к ошибке
        ]

        for data in invalid_data:
            with self.assertRaises(ValidationError):
                LessonParser(**data)

    def test_group_id_validation(self):
        """Проверка на корректную обработку group_id"""
        valid_data = [
            {"lesson_number": 5, "group_id": 101},
            {"lesson_number": 5, "group_id": '101'},  # Строка, которая будет приведена к числу
        ]

        for data in valid_data:
            lesson_parser = LessonParser(**data)
            self.assertEqual(lesson_parser.group_id, int(data['group_id']))

        # Проверка на отрицательное число
        invalid_data = [
            {"lesson_number": 5, "group_id": -1},
            {"lesson_number": 5, "group_id": ''},  # Пустая строка должна вызвать ошибку
        ]

        for data in invalid_data:
            with self.assertRaises(ValidationError):
                LessonParser(**data)
