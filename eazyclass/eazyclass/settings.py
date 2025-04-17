"""
Django settings for eazyclass project.

Generated by 'django-admin startproject' using Django 5.0.4.

For more information on this file, see
https://docs.djangoproject.com/en/5.0/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.0/ref/settings/
"""

from datetime import timedelta
from pathlib import Path
import os
from dotenv import load_dotenv

load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
# DEBUG = os.getenv('DEBUG') == 'True'
DEBUG = False


DEBUG_TOOLBAR_CONFIG = {
    'IS_RUNNING_TESTS': False,  # Отключение панели инструментов при тестах
}

ALLOWED_HOSTS = [
    'localhost',
    '127.0.0.1',
]

INTERNAL_IPS = [
    '127.0.0.1',
]

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_filters',
    'rest_framework',
    'rest_framework_json_api',
    'rest_framework_simplejwt',
    'django_celery_beat',
    'rangefilter',
    'debug_toolbar',
    'scheduler',
    'scrapy_app',
    'utils',
]

MIDDLEWARE = [
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'eazyclass.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'eazyclass.wsgi.application'

# Database
# https://docs.djangoproject.com/en/5.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('POSTGRES_DB'),
        'USER': os.getenv('POSTGRES_USER'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD'),
        'HOST': os.getenv('POSTGRES_HOST'),
        'PORT': os.getenv('POSTGRES_PORT'),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.0/ref/settings/#auth-password-validators

AUTH_USER_MODEL = 'scheduler.User'

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.0/topics/i18n/

LANGUAGE_CODE = 'ru-ru'

TIME_ZONE = 'Europe/Moscow'

USE_I18N = True

USE_TZ = True

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.0/howto/static-files/

STATIC_URL = 'static/'

# Для разработки:
STATICFILES_DIRS = [
    BASE_DIR / 'scheduler/static',
]

# Для продакшена:
STATIC_ROOT = BASE_DIR / 'static/'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
# https://docs.djangoproject.com/en/5.0/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
        'verbose': {
            'format': '{levelname} {asctime} {module} {process} {thread} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.FileHandler',
            'filename': 'celery.log',
            'formatter': 'verbose',
            'encoding': 'utf-8',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': True,
        },
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'celery': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'scrapy': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'telegrambot': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    }
}

REDIS_CONFIG = {
    'default': os.getenv('REDIS_DEFAULT_CACHE_URL'),
    'auth': os.getenv('REDIS_AUTH_CACHE_URL'),
    'telegrambot': os.getenv('REDIS_TELEGRAM_BOT_CACHE_URL'),
    'scrapy': os.getenv('REDIS_SCRAPY_URL'),
}

CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_CONFIG['default'],
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'default',
    },
    'whitelist': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_CONFIG['auth'],
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'refresh_token',
    },
    'auth': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': REDIS_CONFIG['auth'],
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        },
        'KEY_PREFIX': 'nonce',
    },
}

from rest_framework.authentication import SessionAuthentication

REST_FRAMEWORK = {
    'DEFAULT_PARSER_CLASSES': (
        'rest_framework_json_api.parsers.JSONParser',
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser'
    ),

    'DEFAULT_RENDERER_CLASSES': (
        'rest_framework_json_api.renderers.JSONRenderer',
        # 'rest_framework.renderers.JSONRenderer',
        # 'scheduler.api.renderers.APIJSONRenderer',
        # 'rest_framework.renderers.BrowsableAPIRenderer',
    ),

    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'scheduler.authentication.HMACAuthentication',
    ),

    # 'EXCEPTION_HANDLER': 'scheduler.api.exceptions.custom_exception_handler',
    'EXCEPTION_HANDLER': 'rest_framework_json_api.exceptions.exception_handler',

    'DEFAULT_METADATA_CLASS': 'rest_framework_json_api.metadata.JSONAPIMetadata',

    'DEFAULT_FILTER_BACKENDS': (
        'rest_framework_json_api.filters.QueryParameterValidationFilter',
        'rest_framework_json_api.filters.OrderingFilter',
        'rest_framework_json_api.django_filters.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
    ),

    'DEFAULT_SCHEMA_CLASS': 'rest_framework_json_api.schemas.openapi.AutoSchema',
    'SEARCH_PARAM': 'filter[search]',

}

JSON_API_UNIFORM_EXCEPTIONS = True


SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': False,
    'UPDATE_LAST_LOGIN': True,

    "SIGNING_KEY": SECRET_KEY,

    'AUTH_HEADER_TYPES': ('Bearer',),


    "TOKEN_OBTAIN_SERIALIZER": "schedule.api.v1.serializers.CustomTokenObtainPairSerializer",
    "TOKEN_REFRESH_SERIALIZER": "schedule.api.v1.serializers.CustomTokenRefreshSerializer",
}

REDIS_SCRAPY_URL = os.getenv('REDIS_SCRAPY')

CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL')
CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
# Параметры для управления задачами
CELERYD_POOL = 'prefork'  # Использование пула процессов
CELERYD_CONCURRENCY = 4  # 4 рабочих процесса

BASE_SCRAPING_URL = os.getenv('BASE_SCRAPING_URL')

BOT_SOCIAL_ID = os.getenv('BOT_SOCIAL_ID')
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME')
TELEGRAM_REDIS_STORAGE_URL = os.getenv('TELEGRAM_REDIS_STORAGE_URL')

AUTH_DEEPLINK_TEMPLATES = {
    'telegram': f'https://t.me/{TELEGRAM_BOT_USERNAME}?start={{nonce}}',
    'vk': f'https://vk.com/<bot_name>?start={{nonce}}',
}

BOT_HMAC_SECRETS = {
    'telegram': os.getenv('TELEGRAM_HMAC_SECRET'),
    'vk': os.getenv('VK_HMAC_SECRET'),
}
