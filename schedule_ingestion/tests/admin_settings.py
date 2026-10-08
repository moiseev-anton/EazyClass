from .publication_settings import *

INSTALLED_APPS = [*INSTALLED_APPS, 'django.contrib.admin.apps.SimpleAdminConfig',
                  'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles']
MIDDLEWARE = ['django.contrib.sessions.middleware.SessionMiddleware',
              'django.middleware.csrf.CsrfViewMiddleware',
              'django.contrib.auth.middleware.AuthenticationMiddleware',
              'django.contrib.messages.middleware.MessageMiddleware']
TEMPLATES = [{'BACKEND': 'django.template.backends.django.DjangoTemplates', 'APP_DIRS': True,
              'OPTIONS': {'context_processors': ['django.template.context_processors.request',
                  'django.contrib.auth.context_processors.auth', 'django.contrib.messages.context_processors.messages']}}]
ROOT_URLCONF = 'schedule_ingestion.tests.admin_urls'
STATIC_URL = '/static/'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
