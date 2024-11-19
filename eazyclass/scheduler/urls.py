from django.urls import path
from .admin import LessonTimeTemplateAdmin
from .views import home_view

urlpatterns = [
    path('admin/scheduler/lessontimetemplate/apply-template-changes/', LessonTimeTemplateAdmin.apply_template_changes, name='apply_template_changes'),
    path('test/', home_view, name='test'),
    path('schedule/', home_view, name='test'),
    path('list/', home_view, name='test'),
    path('notifications/', home_view, name='test'),
]