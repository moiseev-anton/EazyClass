"""Logging regression tests without dotenv or external services."""
from .sync_settings import *

CACHES = {
    alias: {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": f"logging-tests-{alias}",
    }
    for alias in ("default", "auth", "whitelist")
}
