from django.urls import path
from .admin import LessonTimeTemplateAdmin

urlpatterns = [
    path('admin/scheduler/lessontimetemplate/apply-template-changes/', LessonTimeTemplateAdmin.apply_template_changes, name='apply_template_changes'),
]