from datetime import timedelta
from unittest.mock import Mock, patch

from django.contrib.admin.widgets import AutocompleteSelect
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from scheduler.activities.admin_query_actions import replace_lesson_related_fields
from scheduler.forms import ReplaceLessonRelatedFieldsForm
from scheduler.models import Lesson, LessonAnnotation, Subject


urlpatterns = []


@override_settings(ROOT_URLCONF=__name__)
class LessonBulkAnnotationTests(TestCase):
    def setUp(self):
        self.annotation = LessonAnnotation.objects.create(title="Exam")
        self.selected = Lesson.objects.create(annotation=self.annotation)
        self.other = Lesson.objects.create(annotation=self.annotation)
        self.old_time = timezone.now() - timedelta(days=1)
        Lesson.objects.update(updated_at=self.old_time)
        self.modeladmin = Mock()

    def apply(self, data):
        request = RequestFactory().post("/admin/scheduler/lesson/", {"apply": "1", **data})
        return replace_lesson_related_fields(
            self.modeladmin, request, Lesson.objects.filter(pk=self.selected.pk)
        )

    def assert_only_selected_updated(self):
        self.selected.refresh_from_db()
        self.other.refresh_from_db()
        self.assertGreater(self.selected.updated_at, self.old_time)
        self.assertEqual(self.other.updated_at, self.old_time)
        self.assertEqual(self.other.annotation_id, self.annotation.pk)

    def test_assign_annotation(self):
        replacement = LessonAnnotation.objects.create(title="Online")
        self.assertEqual(self.apply({"annotation": replacement.pk}).status_code, 302)
        self.assert_only_selected_updated()
        self.assertEqual(self.selected.annotation_id, replacement.pk)

    def test_clear_annotation(self):
        self.assertEqual(self.apply({"clear_annotation": "on"}).status_code, 302)
        self.assert_only_selected_updated()
        self.assertIsNone(self.selected.annotation_id)

    def test_blank_annotation_preserves_value_when_changing_subject(self):
        subject = Subject.objects.create(title="Math")
        self.apply({"subject": subject.pk, "annotation": ""})
        self.assert_only_selected_updated()
        self.assertEqual(self.selected.annotation_id, self.annotation.pk)
        self.assertEqual(self.selected.subject_id, subject.pk)

    def test_conflicting_selection_is_rejected_without_update(self):
        with patch("scheduler.activities.admin_query_actions.render") as render:
            self.apply({"annotation": self.annotation.pk, "clear_annotation": "on"})
        form = render.call_args.args[2]["form"]
        self.assertFalse(form.is_valid())
        self.assertTrue(form.non_field_errors())
        self.assertIsInstance(form.fields["annotation"].widget, AutocompleteSelect)
        self.selected.refresh_from_db()
        self.assertEqual(self.selected.annotation_id, self.annotation.pk)
        self.assertEqual(self.selected.updated_at, self.old_time)
        self.modeladmin.message_user.assert_not_called()

    def test_empty_submission_is_rejected(self):
        form = ReplaceLessonRelatedFieldsForm({"annotation": ""})
        self.assertFalse(form.is_valid())

    def test_invalid_annotation_is_rejected(self):
        form = ReplaceLessonRelatedFieldsForm({"annotation": "invalid"})
        self.assertFalse(form.is_valid())
        self.assertIn("annotation", form.errors)
