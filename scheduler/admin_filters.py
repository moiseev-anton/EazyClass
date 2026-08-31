from datetime import date

from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from django.db.models import Count, Exists, OuterRef, Q
from rangefilter.filters import DateRangeFilter

from scheduler.models import Lesson


class RelatedExistsFilter(admin.SimpleListFilter):
    """
    Универсальный фильтр для проверки наличия связанных объектов.

    Нужно указать:
        related_name — имя related_name связи
        title — название фильтра в админке
    """

    title = "related"
    parameter_name = "related_exists"
    related_name = None

    def lookups(self, request, model_admin):
        return (
            ("yes", "Есть"),
            ("no", "Нет"),
        )

    def queryset(self, request, queryset):
        if not self.related_name:
            return queryset

        queryset = queryset.annotate(
            _related_count=Count(self.related_name)
        )

        if self.value() == "yes":
            return queryset.filter(_related_count__gt=0)

        if self.value() == "no":
            return queryset.filter(_related_count=0)

        return queryset


# ---------------------------------------------------------------------------
# Фильтры наличия связанных записей
# ---------------------------------------------------------------------------
class TeacherHasLessonsFilter(RelatedExistsFilter):
    title = "lessons exist"
    parameter_name = "lessons_exist"
    related_name = "lessons"


class GroupHasLessonsFilter(RelatedExistsFilter):
    title = "lessons exist"
    parameter_name = "lessons_exist"
    related_name = "lessons"


class SubjectHasLessonsFilter(RelatedExistsFilter):
    title = "lessons exist"
    parameter_name = "lessons_exist"
    related_name = "lessons"


class ClassroomHasLessonsFilter(RelatedExistsFilter):
    title = "lessons exist"
    parameter_name = "lessons_exist"
    related_name = "lessons"

class UserHasSubscriptionFilter(RelatedExistsFilter):
    title = "Subscription"
    parameter_name = "subscriptions_exist"
    related_name = "subscriptions"


class TeacherNoLessonsSinceDateFilter(DateRangeFilter):
    """Teachers without lessons in the selected date range.

    The UI uses the same rangefilter datepicker as the Lesson admin, but the
    filtering logic is inverted: keep only teachers who have no lessons whose
    period.date falls in the selected window.
    """
    def __init__(self, field, request, params, model, model_admin, field_path):
        super().__init__(field, request, params, model, model_admin, field_path)
        self.title = "Нет занятий"

    def queryset(self, request, queryset):
        if not self.form.is_valid():
            return queryset

        cleaned_data = dict(self.form.cleaned_data.items())
        if not cleaned_data:
            return queryset

        from_date = cleaned_data.get(self.lookup_kwarg_gte)
        to_date = cleaned_data.get(self.lookup_kwarg_lte)

        if from_date is None and to_date is None:
            return queryset

        lessons_qs = Lesson.objects.filter(teacher_id=OuterRef("pk"))

        if from_date is not None:
            lessons_qs = lessons_qs.filter(period__date__gte=from_date)
        if to_date is not None:
            lessons_qs = lessons_qs.filter(period__date__lte=to_date)

        return queryset.annotate(
            _has_lessons_in_range=Exists(lessons_qs)
        ).filter(_has_lessons_in_range=False)


# ---------------------------------------------------------------------------
# Autocomplete filters
# ---------------------------------------------------------------------------

class GroupFilter(AutocompleteFilter):
    """Filter lessons by `group` using autocomplete."""
    title = 'Group'
    field_name = 'group'


class TeacherFilter(AutocompleteFilter):
    """Filter lessons by `teacher` using autocomplete."""
    title = 'Teacher'
    field_name = 'teacher'


class SubjectFilter(AutocompleteFilter):
    """Filter lessons by `subject` using autocomplete."""
    title = 'Subject'
    field_name = 'subject'


class FacultyFilter(AutocompleteFilter):
    """Filter groups by `faculty` using autocomplete."""
    title = 'Faculty'
    field_name = 'faculty'


class ClassroomFilter(AutocompleteFilter):
    """Filter groups by `faculty` using autocomplete."""
    title = 'Classroom'
    field_name = 'classroom'