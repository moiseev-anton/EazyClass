"""Only for the disposable subprocess worker started by test_worker_crash."""
from .publication_postgres_settings import *

DATABASES['default']['NAME'] = 'test_tableparser_validation'
