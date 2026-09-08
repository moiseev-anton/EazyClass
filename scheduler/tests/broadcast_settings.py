"""Isolated database tests: no dotenv, Redis, Telegram or production database."""
SECRET_KEY = "broadcast-tests-only"
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "polymorphic", "scheduler"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
AUTH_USER_MODEL = "scheduler.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TELEGRAM_BOT_TOKEN = ""
# Existing historical scheduler migrations cannot build a fresh database (an
# index rename references a missing LessonBuffer index). Test current models.
MIGRATION_MODULES = {"scheduler": None}
