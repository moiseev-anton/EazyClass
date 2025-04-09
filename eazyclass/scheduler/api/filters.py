import django_filters
from rest_framework.exceptions import ValidationError

from scheduler.models import Lesson


class LessonFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name="period__date", lookup_expr="gte")
    date_to = django_filters.DateFilter(field_name="period__date", lookup_expr="lte")
    subgroup = django_filters.CharFilter(field_name="subgroup")

    class Meta:
        model = Lesson
        fields = []

    def filter_queryset(self, queryset):
        date_from = self.form.cleaned_data.get("date_from")
        date_to = self.form.cleaned_data.get("date_to")

        if date_from and date_to:
            delta = (date_to - date_from).days
            if delta < 0:
                raise ValidationError({"detail": "Дата окончания раньше даты начала"})
            if delta > 31:  # Жёсткий лимит
                raise ValidationError(
                    {"detail": "Превышен максимальный диапазон (31 день)"}
                )

        return super().filter_queryset(queryset)
