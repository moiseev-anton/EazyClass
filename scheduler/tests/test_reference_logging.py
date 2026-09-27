import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scheduler.tasks import refresh
from scheduler.fetched_data_sync.faculties import updater as faculties
from scheduler.fetched_data_sync.teachers import updater as teachers
from scheduler.fetched_data_sync import utils


@pytest.mark.parametrize("name,service", [
    ("refresh_groups", "refresh_faculties_and_groups"),
    ("refresh_teachers", "refresh_teachers_endpoints"),
])
@pytest.mark.parametrize("retries,outcome,level", [
    (0, "retry_requested", logging.WARNING), (3, "failed", logging.ERROR),
])
def test_refresh_failure_is_safe_and_never_claims_completion(monkeypatch, caplog, name, service,
                                                          retries, outcome, level):
    caplog.set_level(logging.INFO)
    task = getattr(refresh, name)
    error = RuntimeError("secret-response-body")
    monkeypatch.setattr(refresh, service, Mock(side_effect=error))
    retry = Mock(side_effect=error)
    monkeypatch.setattr(task, "retry", retry)
    task.push_request(retries=retries)
    try:
        with pytest.raises(RuntimeError):
            task.run()
    finally:
        task.pop_request()
    records = [r for r in caplog.records if getattr(r, "outcome", None)]
    assert len(records) == 1
    assert records[0].outcome == outcome and records[0].levelno == level
    assert records[0].attempt == retries + 1
    assert "secret-response-body" not in caplog.text
    retry.assert_called_once_with(exc=error)


def test_invalid_faculties_page_is_not_logged_or_written(monkeypatch, caplog):
    monkeypatch.setattr(faculties, "fetch_page_content", lambda _: b"<html>secret-body</html>")
    writes = Mock()
    monkeypatch.setattr(faculties.Faculty.objects, "get_or_create", writes)
    with pytest.raises(RuntimeError):
        faculties.refresh_faculties_and_groups("https://example.invalid/", "groups")
    writes.assert_not_called()
    assert "secret-body" not in caplog.text


def test_fetch_failure_propagates_without_duplicate_or_sensitive_log(monkeypatch, caplog):
    monkeypatch.setattr(utils.requests, "get", Mock(side_effect=utils.requests.RequestException("secret-url")))
    with pytest.raises(utils.requests.RequestException):
        utils.fetch_page_content("https://example.invalid/?token=secret-url")
    assert not caplog.records


def test_teacher_counts_include_ambiguous_and_missing_matches(monkeypatch, caplog):
    entries = [SimpleNamespace(short_name=name, endpoint=endpoint, save=Mock()) for name, endpoint in
               [("First", None), ("Second", "same"), ("Private Name", "one"), ("Private Name", "two")]]
    monkeypatch.setattr(teachers, "fetch_page_content", lambda _: b"")
    monkeypatch.setattr(teachers, "parse_teachers_page", lambda *_: {
        "First": "new", "Second": "same", "Private Name": "ambiguous", "Missing": "missing"})
    monkeypatch.setattr(teachers.Teacher.objects, "filter", lambda **_: entries)
    result = teachers.refresh_teachers_endpoints("https://example.invalid/", "teachers")
    assert result == {"count": 4, "updated_count": 1, "unchanged_count": 1, "unmatched_count": 2}
    entries[0].save.assert_called_once_with(update_fields=["endpoint"])
    for entry in entries[1:]:
        entry.save.assert_not_called()
    assert "Private Name" not in caplog.text


@pytest.mark.parametrize("count,unmatched,outcome,level", [
    (3, 0, "success", logging.INFO), (3, 2, "partial", logging.WARNING),
    (0, 0, "empty", logging.WARNING),
])
def test_teacher_task_reports_coverage(monkeypatch, caplog, count, unmatched, outcome, level):
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(refresh, "refresh_teachers_endpoints", lambda **_: {
        "count": count, "updated_count": 0, "unchanged_count": count - unmatched,
        "unmatched_count": unmatched})
    refresh.refresh_teachers.run()
    record = next(r for r in caplog.records if getattr(r, "event", "") == "reference.teachers.completed")
    assert record.outcome == outcome and record.levelno == level
    assert record.duration_ms >= 0
