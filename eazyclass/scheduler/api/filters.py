from django_filters import rest_framework as filters
from rest_framework.exceptions import ValidationError
from datetime import timedelta
from scheduler.models import Lesson


class LessonFilter(filters.FilterSet):
    date_from = filters.DateFilter(field_name='period__date', lookup_expr='gte', required=True)
    date_to = filters.DateFilter(field_name='period__date', lookup_expr='lte', required=True)
    subgroup = filters.CharFilter(field_name='subgroup', lookup_expr='exact')
    format = filters.CharFilter(method='ignore_format_filter')

    class Meta:
        model = Lesson
        fields = ['date_from', 'date_to', 'subgroup']

    def ignore_format_filter(self, queryset, name, value):
        return queryset

    def filter_queryset(self, queryset):
        # Проверяем диапазон дат
        date_from = self.form.cleaned_data.get('date_from')
        date_to = self.form.cleaned_data.get('date_to')

        if date_from and date_to:
            if date_to < date_from:
                raise ValidationError("End date must be after start date.")
            if (date_to - date_from) > timedelta(days=31):
                raise ValidationError("Date range cannot exceed 31 days.")

        return super().filter_queryset(queryset)


