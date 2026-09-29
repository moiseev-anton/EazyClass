"""Generate the public schema in a clean process, independent of DRF import order."""
import os
from pathlib import Path
import subprocess
import sys


def test_public_schema_describes_hmac_and_subscription_filters():
    script = r''' 
import django
from django.conf import settings
settings.REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "scheduler.authentication.HMACAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ["rest_framework_json_api.django_filters.backends.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "drf_spectacular_jsonapi.schemas.pagination.JsonApiPageNumberPagination",
}
django.setup()
from drf_spectacular.generators import SchemaGenerator
from scheduler.api.v1.urls import public_urlpatterns
schema = SchemaGenerator(patterns=public_urlpatterns).get_schema(request=None, public=True)
schemes = schema['components']['securitySchemes']
headers = {'hmacSignature': 'X-Signature', 'hmacTimestamp': 'X-Timestamp',
           'hmacPlatform': 'X-Platform', 'hmacSocialId': 'X-Social-ID'}
for name, header in headers.items():
    assert schemes[name]['type'] == 'apiKey'
    assert schemes[name]['in'] == 'header'
    assert schemes[name]['name'] == header
operation = schema['paths']['/subscriptions/']['get']
assert {name: [] for name in headers} in operation['security']
assert {'jwtAuth': []} in operation['security']
parameters = {p['name']: p for p in operation['parameters']}
for name in ('filter[group]', 'filter[teacher]'):
    assert parameters[name]['schema']['type'] == 'integer'
'''
    env = {**os.environ, "DJANGO_SETTINGS_MODULE": "scheduler.tests.logging_settings"}
    result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[2],
                            env=env, capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    assert "could not resolve authenticator" not in result.stderr
    assert "Unable to guess choice types" not in result.stderr
