from datetime import date

from django.test import TestCase

from scheduler.forms import LessonAdminForm
from scheduler.models import Classroom, Group, Lesson, Period, Subject


class LessonAdminPeriodTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(title="A1")
        self.subject = Subject.objects.create(title="Math")
        self.classroom = Classroom.objects.create(title="101")
        self.day = date(2026, 9, 9)

    def form(self, part=0, instance=None):
        return LessonAdminForm(data={
            "date": self.day.isoformat(),
            "lesson_number": 1,
            "part": part,
            "group": self.group.pk,
            "subject": self.subject.pk,
            "classroom": self.classroom.pk,
            "subgroup": "0",
            "is_active": True,
        }, instance=instance)

    def test_new_form_defaults_to_full(self):
        self.assertEqual(LessonAdminForm()["part"].value(), 0)

    def test_edit_form_preserves_period_part(self):
        period = Period.objects.create(date=self.day, lesson_number=1, part=2)
        form = LessonAdminForm(instance=Lesson(period=period))
        self.assertEqual(form["part"].value(), 2)
        self.assertEqual(form["date"].value(), self.day.isoformat())
        self.assertEqual(form["lesson_number"].value(), 1)

    def test_selects_exact_period_when_all_parts_exist(self):
        periods = [Period.objects.create(date=self.day, lesson_number=1, part=part) for part in range(3)]
        lesson = Lesson.objects.create(period=periods[0])
        for period in periods:
            with self.subTest(part=period.part):
                form = self.form(part=period.part, instance=lesson)
                self.assertTrue(form.is_valid(), form.errors)
                form.save()
                lesson.refresh_from_db()
                self.assertEqual(lesson.period_id, period.pk)
        self.assertEqual(Period.objects.count(), 3)

    def test_creates_missing_period_for_each_part(self):
        for part in range(3):
            with self.subTest(part=part):
                form = self.form(part=part)
                self.assertTrue(form.is_valid(), form.errors)
                lesson = form.save()
                self.assertEqual(lesson.period.date, self.day)
                self.assertEqual(lesson.period.lesson_number, 1)
                self.assertEqual(lesson.period.part, part)
        self.assertEqual(Period.objects.count(), 3)

    def test_commit_false_resolves_period_without_saving_lesson(self):
        form = self.form(part=1)
        self.assertTrue(form.is_valid(), form.errors)
        lesson = form.save(commit=False)
        self.assertIsNone(lesson.pk)
        self.assertFalse(Lesson.objects.exists())
        self.assertEqual(lesson.period_id, Period.objects.get(part=1).pk)
        lesson.save()
        form.save_m2m()
        self.assertEqual(Lesson.objects.get().period.part, 1)

    def test_invalid_part_is_rejected(self):
        for part in ("", "invalid", 3):
            with self.subTest(part=part):
                form = self.form(part=part)
                self.assertFalse(form.is_valid())
                self.assertIn("part", form.errors)
        self.assertFalse(Period.objects.exists())
