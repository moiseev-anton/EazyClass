import django_filters
from scheduler.models import Lesson
from rest_framework.exceptions import ValidationError


# class LessonFilter(django_filters.FilterSet):
#     group_id = django_filters.NumberFilter(field_name='group__id')
#     teacher_id = django_filters.NumberFilter(field_name='teacher__id')
#     date = django_filters.DateFilter(field_name='period__date')
#     date_after = django_filters.DateFilter(field_name='period__date', lookup_expr='gte')  # >=
#     date_before = django_filters.DateFilter(field_name='period__date', lookup_expr='lte')  # <=
#
#     class Meta:
#         model = Lesson
#         fields = ['group_id', 'teacher_id', 'date', 'date_after', 'date_before']


class LessonFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(field_name='period__date')
    date_from = django_filters.DateFilter(field_name='period__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='period__date', lookup_expr='lte')
    subgroup = django_filters.CharFilter(field_name='subgroup')

    class Meta:
        model = Lesson
        fields = {
            'group': ['exact'],
            'teacher': ['exact'],
            'period__date': ['exact', 'gte', 'lte'],
        }

    def filter_queryset(self, queryset):
        if not self.form.is_valid() or not any(self.form.cleaned_data.values()):
            raise ValidationError({
                "code": 400,
                "detail": "At least one filter (group__id, teacher__id, period__date, date_from, or date_to) is required"
            })
        return super().filter_queryset(queryset)
