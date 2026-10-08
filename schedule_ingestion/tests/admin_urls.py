from django.contrib import admin
from django.urls import path
import schedule_ingestion.admin  # Register only ingestion; avoid unrelated admin integrations in isolated tests.

urlpatterns = [path('admin/', admin.site.urls)]
