from datetime import date

from django.test import TestCase
from scheduler.tasks.schedule_parser import LessonDict


class TestLessonDict(TestCase):

    def test_lesson_dict_initialization(self):
        """Тест инициализации LessonDict"""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=1,
            _date=date(2024, 12, 1),
            group_id=123
        )

        self.assertEqual(lesson.lesson_number, 1)
        self.assertEqual(lesson.subject_title, "Math")
        self.assertEqual(lesson.classroom_title, "Room 101")
        self.assertEqual(lesson.teacher_fullname, "John Doe")
        self.assertEqual(lesson.subgroup, 1)
        self.assertEqual(lesson.date, date(2024, 12, 1))
        self.assertEqual(lesson.group_id, 123)

    def test_subject_title_max_length(self):
        """Проверка, что subject_title ограничивается максимальной длиной."""
        long_title = "A" * (LessonDict.MAX_SUBJECT_TITLE_LENGTH + 1)  # Длиннее максимально допустимого
        lesson = LessonDict(
            lesson_number=1,
            subject_title=long_title,
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=1
        )
        self.assertEqual(lesson.subject_title, "A" * LessonDict.MAX_SUBJECT_TITLE_LENGTH)

    def test_teacher_fullname_max_length(self):
        """Проверка, что teacher_fullname ограничивается максимальной длиной."""
        long_name = "A" * (LessonDict.MAX_TEACHER_FULLNAME_LENGTH + 1)
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname=long_name,
            subgroup=1
        )
        self.assertEqual(lesson.teacher_fullname, "A" * LessonDict.MAX_TEACHER_FULLNAME_LENGTH)

    def test_lesson_number_setter(self):
        """Тестирование setter для lesson_number."""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=1
        )
        lesson.lesson_number = 5
        self.assertEqual(lesson.lesson_number, 5)

    def test_invalid_lesson_number(self):
        """Тестирование setter для lesson_number с некорректным значением."""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=1
        )
        with self.assertRaises(ValueError):
            lesson.lesson_number = -1  # Вне диапазона
        with self.assertRaises(ValueError):
            lesson.lesson_number = "invalid"  # Некорректный тип

    def test_subgroup_setter(self):
        """Тестирование setter для subgroup."""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=0
        )
        self.assertEqual(lesson.subgroup, 0)

    def test_invalid_subgroup(self):
        """Тестирование setter для subgroup с некорректным значением."""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=0
        )
        with self.assertRaises(ValueError):
            lesson.subgroup = -1  # Вне диапазона
        with self.assertRaises(ValueError):
            lesson.subgroup = "invalid"  # Некорректный тип

    def test_date_setter(self):
        """Тестирование setter для date."""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=1
        )
        lesson.date = date(2024, 12, 1)
        self.assertEqual(lesson.date, date(2024, 12, 1))

    def test_invalid_date_format(self):
        """Тестирование setter для date с некорректным форматом."""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=1
        )
        with self.assertRaises(ValueError):
            lesson.date = "01.12.2024"  # Некорректный формат для date, ожидается объект типа date

    def test_invalid_type_for_date(self):
        """Тестирование setter для date с некорректным типом."""
        lesson = LessonDict(
            lesson_number=1,
            subject_title="Math",
            classroom_title="Room 101",
            teacher_fullname="John Doe",
            subgroup=1
        )
        with self.assertRaises(TypeError):
            lesson.date = 123  # Некорректный тип
