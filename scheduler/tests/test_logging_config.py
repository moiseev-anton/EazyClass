import json
import logging
import os
from pathlib import Path
import subprocess
import sys

import pytest

from eazyclass.logging_config import EventFormatter, build_logging_config, safe_error_context


def make_record(**extra):
    record = logging.LogRecord("scheduler.test", logging.INFO, __file__, 1,
                               "Пользователь %s авторизован", (42,), None)
    record.__dict__.update(extra)
    return record


@pytest.mark.parametrize("style", ["json", "text"])
def test_formats_include_human_message_event_and_context(style):
    output = EventFormatter(style=style).format(make_record(
        event="auth.bot.completed", user_id=42, user_created=False,
    ))
    assert "Пользователь 42 авторизован" in output
    assert "auth.bot.completed" in output
    assert "user_id" in output
    if style == "json":
        data = json.loads(output)
        assert data["user_id"] == 42
        assert data["user_created"] is False
        assert data["timestamp"].endswith("+00:00")


@pytest.mark.parametrize("style", ["json", "text"])
def test_extras_are_allowlisted_without_serializing_objects(style):
    class Sensitive:
        def __str__(self):
            raise AssertionError("Must not stringify arbitrary extras")
        __repr__ = __str__

    record = make_record(
        nonce="secret-nonce", password="secret-password", request=Sensitive(),
        headers={"Authorization": "secret-header"}, user_id=Sensitive(),
        error_stack=[{"error_type": "RuntimeError", "password": "secret-nested"}],
    )
    output = EventFormatter(style=style).format(record)
    assert "secret-" not in output
    assert "[omitted]" in output


@pytest.mark.parametrize("style", ["json", "text"])
def test_exception_chain_keeps_locations_without_values_or_cached_traceback(style):
    try:
        try:
            raise ValueError("secret-inner")
        except ValueError as inner:
            raise RuntimeError("secret-outer") from inner
    except RuntimeError as exc:
        record = make_record(**safe_error_context(exc))
        record.exc_info = sys.exc_info()
        # Another formatter may previously have filled this cache.
        record.exc_text = "secret-cached-traceback"
        record.stack_info = "secret-source-line"
        output = EventFormatter(style=style).format(record)
    assert "secret-" not in output
    assert "RuntimeError" in output and "ValueError" in output
    assert "test_logging_config.py" in output
    assert "test_exception_chain_keeps_locations" in output
    assert record.exc_text == "secret-cached-traceback"  # No record mutation.


def test_formats_escape_newlines_and_support_legacy_records():
    record = make_record()
    record.msg, record.args = "First\nsecond\rthird", ()
    for style in ("text", "json"):
        output = EventFormatter(style=style).format(record)
        assert len(output.splitlines()) == 1
        assert "log.message" in output


def test_config_defaults_and_validation():
    assert build_logging_config(debug=True)["formatters"]["event"]["style"] == "text"
    assert build_logging_config()["formatters"]["event"]["style"] == "json"
    for args in ({"log_format": "invalid"}, {"level": "invalid"}):
        with pytest.raises(ValueError):
            build_logging_config(**args)


@pytest.mark.parametrize("framework", ["django", "celery", "scrapy"])
def test_framework_setup_outputs_each_event_once_in_json(framework):
    # Isolate logging global state and Twisted's reactor from pytest/Django.
    script = '''
import json, logging, logging.config
import django
django.setup()
from django.conf import settings
from eazyclass.logging_config import build_logging_config
settings.LOGGING = build_logging_config(service="test", level="DEBUG")
FRAMEWORK_SETUP
for name in ("scheduler.probe", "celery.task", "scrapy_app.probe", "schedule_spider"):
    logging.getLogger(name).info("Проверка", extra={"event": "test.probe", "user_id": 42})
'''
    setup = {
        "django": "logging.config.dictConfig(settings.LOGGING)",
        "celery": '''from eazyclass.celery import app
app.log.setup_logging_subsystem(loglevel="DEBUG")''',
        "scrapy": '''import scrapy
from scheduler.tasks.scraping import SpiderRunner
class Probe(scrapy.Spider):
    name = "probe"
    start_urls = []
    def closed(self, reason):
        logging.getLogger("scrapy_app.probe").info("Паук завершён", extra={"event": "test.spider_context"})
SpiderRunner(Probe)._crawl({"run_id": "spider-run", "task_id": "spider-task", "attempt": 2})''',
    }[framework]
    result = subprocess.run(
        [sys.executable, "-c", script.replace("FRAMEWORK_SETUP", setup)],
        cwd=Path(__file__).resolve().parents[2],
        env={**os.environ, "DJANGO_SETTINGS_MODULE": "scheduler.tests.logging_settings",
             "PYTHONIOENCODING": "utf-8"},
        capture_output=True, text=True, encoding="utf-8", timeout=30,
    )
    assert result.returncode == 0, result.stderr
    records = [json.loads(line) for line in result.stderr.splitlines()]
    probes = [r for r in records if r.get("event") == "test.probe"]
    assert len(probes) == 4, result.stderr
    assert len({r["logger"] for r in probes}) == 4
    assert all(r["user_id"] == 42 for r in probes)
    assert all(r["service"] == ("scrapy" if framework == "scrapy" else "test") for r in probes)
    if framework == "scrapy":
        inside = [r for r in records if r.get("event") == "test.spider_context"]
        assert len(inside) == 1
        assert inside[0]["run_id"] == "spider-run"
        assert inside[0]["task_id"] == "spider-task"
        assert inside[0]["attempt"] == 2
        assert all("run_id" not in r for r in probes)
