from datetime import timedelta

from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError

from scheduler.models import Lesson, Group, Faculty


class BaseFilterSetWithFormat(filters.FilterSet):
    format = filters.ChoiceFilter(
        choices=[("full", "Full"), ("compact", "Compact")],
        method="ignore_format_filter",
        required=False,
    )

    def ignore_format_filter(self, queryset, name, value):
        return queryset


class LessonFilter(BaseFilterSetWithFormat):
    LIST_ACTIVITIES = {"list", "by_group", "by_teacher", "get_me"}

    date_from = filters.DateFilter(field_name="period__date", lookup_expr="gte")
    date_to = filters.DateFilter(field_name="period__date", lookup_expr="lte")
    subgroup = filters.CharFilter(field_name="subgroup", lookup_expr="exact")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        view = self.request.parser_context.get("view")
        if view and view.action in self.LIST_ACTIVITIES:
            self.filters["date_from"].extra["required"] = True
            self.filters["date_to"].extra["required"] = True

    class Meta:
        model = Lesson
        fields = ["date_from", "date_to", "subgroup", "format"]

    def filter_queryset(self, queryset):
        # Проверяем диапазон дат
        date_from = self.form.cleaned_data.get("date_from")
        date_to = self.form.cleaned_data.get("date_to")

        if date_from and date_to:
            if date_to < date_from:
                raise ValidationError("End date must be after start date.")
            if (date_to - date_from) > timedelta(days=31):
                raise ValidationError("Date range cannot exceed 31 days.")

        return super().filter_queryset(queryset)


class GroupFilter(BaseFilterSetWithFormat):
    faculty = filters.ModelChoiceFilter(
        field_name="faculty",
        queryset=Faculty.objects.filter(is_active=True),
        to_field_name="id",
        required=False,
    )
    grade = filters.NumberFilter(field_name="grade", required=False)

    class Meta:
        model = Group
        fields = ["faculty", "grade", "format"]
