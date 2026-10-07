from django.apps import AppConfig


class ScheduleIngestionConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "schedule_ingestion"
    verbose_name = "Поступление расписания"

    def ready(self):
        from . import sync_events  # noqa: F401
