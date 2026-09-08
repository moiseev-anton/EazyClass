import csv
from datetime import date
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, Mock

import orjson
from django.test import SimpleTestCase, TestCase

from enums import KeyEnum
from scheduler.fetched_data_sync.lessons.lessons_sync_manager import LessonsSyncManager
from scheduler.models import Group, Lesson, LessonAnnotation


# Load the CSV reader without importing unrelated Celery tasks from tasks/__init__.
spec = spec_from_file_location(
    "extract_raw_lessons_for_test",
    Path(__file__).resolve().parents[1] / "tasks" / "extract_raw_lessons.py",
)
extract_raw_lessons = module_from_spec(spec)
spec.loader.exec_module(extract_raw_lessons)


class AnnotationCSVTests(SimpleTestCase):
    def test_optional_annotation_column(self):
        for extra, expected in [
            ({}, None),
            ({"annotation": None}, None),
            ({"annotation": ""}, None),
            ({"annotation": "   "}, None),
            ({"annotation": "  Bring a laptop  "}, "Bring a laptop"),
        ]:
            with self.subTest(extra=extra), TemporaryDirectory() as directory:
                path = Path(directory) / "lessons.csv"
                row = {"group": "A1", "date": "2026-09-08", "lesson_number": "1", **extra}
                with path.open("w", encoding="utf-8", newline="") as file:
                    writer = csv.DictWriter(file, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerow(row)
                lessons, failed = extract_raw_lessons.process_lessons_csv(path, {"a1": 1}, {})
                self.assertEqual(failed, set())
                self.assertEqual(lessons[0]["annotation"], {"title": expected})


class AnnotationSyncTests(TestCase):
    def setUp(self):
        self.group = Group.objects.create(title="A1")
        self.redis = Mock()
        self.manager = LessonsSyncManager(self.redis, start_sync_day=date(2026, 9, 8))

    def item(self, **extra):
        return {
            "group_id": self.group.pk,
            "period": {"date": "2026-09-08", "lesson_number": 1},
            "subject": {"title": "Math"},
            "classroom": {"title": "101"},
            "teacher": {"full_name": None},
            **extra,
        }

    def sync(self, items):
        payload = {
            KeyEnum.SCRAPED_LESSONS: orjson.dumps(items),
            KeyEnum.SCRAPED_GROUPS: orjson.dumps({str(self.group.pk): "hash"}),
            KeyEnum.UNCHANGED_GROUPS: orjson.dumps([]),
        }
        self.redis.get.side_effect = payload.get
        self.redis.pipeline.return_value = MagicMock()
        return self.manager.update_schedule()

    def test_create_reuse_update_clear_and_no_change(self):
        first = LessonAnnotation.objects.create(title="Bring a laptop")
        summary = self.sync([self.item(annotation={"title": "  Bring a laptop  "})])
        lesson = Lesson.objects.get()
        self.assertEqual(lesson.annotation_id, first.pk)
        self.assertEqual(summary["added"][0]["annotation_id"], first.pk)
        self.assertEqual(LessonAnnotation.objects.count(), 1)

        summary = self.sync([self.item(annotation={"title": "Bring a laptop"})])
        self.assertEqual(summary, {"added": [], "updated": [], "removed": []})

        summary = self.sync([self.item(annotation={"title": "Online"})])
        lesson.refresh_from_db()
        second = LessonAnnotation.objects.get(title="Online")
        self.assertEqual(lesson.annotation_id, second.pk)
        self.assertEqual(summary["updated"][0]["annotation_id"], second.pk)
        self.assertEqual(summary["updated"][0]["changes"]["annotation"], [first.pk, second.pk])

        summary = self.sync([self.item()])
        lesson.refresh_from_db()
        self.assertIsNone(lesson.annotation_id)
        self.assertIsNone(summary["updated"][0]["annotation_id"])
        self.assertEqual(summary["updated"][0]["changes"]["annotation"], [second.pk, None])
        self.assertEqual(Lesson.objects.get().pk, lesson.pk)
        self.assertEqual(LessonAnnotation.objects.count(), 2)

    def test_empty_annotations_do_not_create_related_objects(self):
        for extra in [{}, {"annotation": None}, {"annotation": {}}, {"annotation": {"title": None}}, {"annotation": {"title": "  "}}]:
            with self.subTest(extra=extra):
                self.sync([self.item(**extra)])
                self.assertIsNone(Lesson.objects.get().annotation_id)
                self.assertFalse(LessonAnnotation.objects.exists())

    def test_normalized_titles_are_truncated_and_deduplicated(self):
        max_length = LessonAnnotation._meta.get_field("title").max_length
        title = "A" * max_length
        self.sync([
            self.item(annotation={"title": "  " + title + "B"}, subgroup=1),
            self.item(annotation={"title": title + "C"}, subgroup=2),
        ])
        annotation = LessonAnnotation.objects.get()
        self.assertEqual(annotation.title, title)
        self.assertEqual(list(Lesson.objects.values_list("annotation_id", flat=True)), [annotation.pk, annotation.pk])
