from datetime import timedelta

from django.utils.translation import gettext_lazy as _
from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError

from scheduler.models import Lesson, Group, Faculty, Teacher


class LessonFilter(filters.FilterSet):
    date_from = filters.DateFilter(
        field_name="period__date",
        lookup_expr="gte",
        required=True,
        help_text=_(
            "Start date of the period (inclusive).\n"
            "Format: YYYY-MM-DD\n"
            "Maximum date range is 31 days."
        ),
    )
    date_to = filters.DateFilter(
        field_name="period__date",
        lookup_expr="lte",
        required=True,
        help_text=_(
            "End date of the period (inclusive).\n"
            "Format: YYYY-MM-DD\n"
            "Must be equal to or after date_from."
        ),
    )
    subgroup = filters.CharFilter(
        field_name="subgroup",
        lookup_expr="exact",
        help_text=_(
            "Filter by subgroup number. \n" "Possible values: '1', '2' (empty for all)."
        ),
    )
    group = filters.ModelChoiceFilter(
        queryset=Group.objects.filter(is_active=True),
        help_text=_("Filter lessons by group ID."),
    )
    teacher = filters.ModelChoiceFilter(
        queryset=Teacher.objects.filter(is_active=True),
        help_text=_("Filter lessons by teacher ID."),
    )

    class Meta:
        model = Lesson
        fields = ["group", "teacher", "date_from", "date_to", "subgroup"]

    def filter_queryset(self, queryset):
        view = self.request.parser_context.get("view")
        action = getattr(view, "action", None)

        # Только если action — list, требуем наличие group или teacher
        if action == "list":
            group = self.form.cleaned_data.get("group")
            teacher = self.form.cleaned_data.get("teacher")

            if not (group or teacher):
                raise ValidationError(
                    _("At least one of 'group' or 'teacher' filter is required."),
                    code="required",
                )

        # Проверка дат работает всегда
        date_from = self.form.cleaned_data.get("date_from")
        date_to = self.form.cleaned_data.get("date_to")

        if date_from and date_to:
            if date_to < date_from:
                raise ValidationError(_("End date must be after start date."))
            if (date_to - date_from) > timedelta(days=31):
                raise ValidationError(_("Date range cannot exceed 31 days."))

        return super().filter_queryset(queryset)


class GroupFilter(filters.FilterSet):
    faculty = filters.ModelChoiceFilter(
        field_name="faculty",
        queryset=Faculty.objects.filter(is_active=True),
        to_field_name="id",
        required=False,
    )
    grade = filters.NumberFilter(field_name="grade", required=False)

    class Meta:
        model = Group
        fields = ["faculty", "grade"]


class TeacherFilter(filters.FilterSet):
    starts_with = filters.CharFilter(method='filter_starts_with',
        help_text=_("Filter by first letter"),)

    class Meta:
        model = Teacher
        fields = ['starts_with']

    def filter_starts_with(self, queryset, name, value):
        if not value or len(value) != 1 or not value.isalpha():
            raise ValidationError(
                code="invalid_starts_with",
                detail=_("Filter 'starts_with' must be a single alphabetic character.")
            )
        return queryset.filter(full_name__istartswith=value)
