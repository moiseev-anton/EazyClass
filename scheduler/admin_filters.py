from admin_auto_filters.filters import AutocompleteFilter
from django.contrib import admin
from django.db.models import Count


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
    title = "Lessons"
    parameter_name = "lessons_exist"
    related_name = "lessons"


class GroupHasLessonsFilter(RelatedExistsFilter):
    title = "Lessons"
    parameter_name = "lessons_exist"
    related_name = "lessons"


class SubjectHasLessonsFilter(RelatedExistsFilter):
    title = "Lessons"
    parameter_name = "lessons_exist"
    related_name = "lessons"


class ClassroomHasLessonsFilter(RelatedExistsFilter):
    title = "Lessons"
    parameter_name = "lessons_exist"
    related_name = "lessons"

class UserHasSubscriptionFilter(RelatedExistsFilter):
    title = "Subscription"
    parameter_name = "subscriptions_exist"
    related_name = "subscriptions"


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