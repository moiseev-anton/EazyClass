"""Local manual sandbox: isolated DB/Redis, delivery explicitly opt-in."""
import os

from django.core.exceptions import ImproperlyConfigured

if os.environ.get('TABLEPARSER_LOCAL_SANDBOX') != '1':
    raise ImproperlyConfigured('This settings module requires TABLEPARSER_LOCAL_SANDBOX=1')

# Never inherit the developer's or server's dotenv credentials.
os.environ['ENV_FILE'] = '/nonexistent/tableparser-sandbox.env'
from .settings import *  # noqa: E402,F403

DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql', 'HOST': 'parser-sandbox-db', 'PORT': 5432,
    'NAME': 'tableparser_sandbox', 'USER': 'tableparser_sandbox',
    'PASSWORD': os.environ['SANDBOX_DB_PASSWORD'],
}}
CELERY_BROKER_URL = 'redis://parser-sandbox-redis:6379/0'
CELERY_RESULT_BACKEND = 'redis://parser-sandbox-redis:6379/1'
for alias, cache in CACHES.items():
    cache['LOCATION'] = 'redis://parser-sandbox-redis:6379/4'
REDIS_SCRAPY_URL = 'redis://parser-sandbox-redis:6379/2'
TELEGRAM_REDIS_STORAGE_URL = 'redis://parser-sandbox-redis:6379/3'
TABLEPARSER_DISABLE_DELIVERY = os.environ.get('SANDBOX_ENABLE_DELIVERY') != '1'
TABLEPARSER_LOCAL_SANDBOX = True
TABLEPARSER_PUBLIC_BASE_URL = 'http://127.0.0.1:18080'
ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
CSRF_TRUSTED_ORIGINS = ['http://127.0.0.1:18080', 'http://localhost:18080']
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_NAME = 'tableparser_sandbox_session'
CSRF_COOKIE_NAME = 'tableparser_sandbox_csrf'
SECURE_SSL_REDIRECT = False
DEBUG = False
TELEGRAM_BOT_TOKEN = TELEGRAM_ADMIN_BOT_TOKEN = VK_BOT_TOKEN = None
if not TABLEPARSER_DISABLE_DELIVERY:
    TELEGRAM_BOT_TOKEN = os.environ.get('SANDBOX_TELEGRAM_BOT_TOKEN')
    TELEGRAM_ADMIN_BOT_TOKEN = os.environ.get('SANDBOX_TELEGRAM_ADMIN_BOT_TOKEN')
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_BOT_TOKEN:
        raise ImproperlyConfigured('Sandbox delivery requires both sandbox Telegram bot tokens')
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
