from .settings import *
import os

# Explicit local disposable database only; never inherit project .env values.
DATABASES = {'default': {
    'ENGINE': 'django.db.backends.postgresql',
    'HOST': '127.0.0.1',
    'PORT': int(os.environ['TABLEPARSER_TEST_PG_PORT']),
    'NAME': 'tableparser_validation',
    'USER': 'tableparser_validation',
    'PASSWORD': 'local-validation-only',
}}
