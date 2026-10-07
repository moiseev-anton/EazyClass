from .catalog_settings import *

INSTALLED_APPS = [*INSTALLED_APPS, 'django_celery_beat']
BASE_SCRAPING_URL = 'https://example.invalid/'
