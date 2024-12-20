from django.urls import path
from .admin import PeriodTemplateAdmin
from .views import home_view

urlpatterns = [
    path('admin/scheduler/period-template/apply-template-changes/', PeriodTemplateAdmin.apply_template_changes, name='apply_template_changes'),
    path('test/', home_view, name='test'),
    path('schedule/', home_view, name='test'),
    path('list/', home_view, name='test'),
    path('notifications/', home_view, name='test'),
]