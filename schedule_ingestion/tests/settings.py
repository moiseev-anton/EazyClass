"""Isolated migration/import tests; never load project dotenv or external services."""
SECRET_KEY = "ingestion-tests-only"
INSTALLED_APPS = ["schedule_ingestion"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "Europe/Moscow"
