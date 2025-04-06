import django_filters
from scheduler.models import Lesson
from rest_framework.exceptions import ValidationError


class LessonFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name='period__date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='period__date', lookup_expr='lte')
    subgroup = django_filters.CharFilter(field_name='subgroup')

    class Meta:
        model = Lesson
        fields = {
            'period__date': ['gte', 'lte'],
        }
