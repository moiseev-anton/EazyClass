import logging
from unittest.mock import Mock

import orjson
import pytest
from celery import chain

from enums import KeyEnum
from scheduler.tasks import extract_raw_lessons as importer
from scheduler.tasks.synchronisation import sync_lessons


@pytest.fixture
def source(tmp_path, monkeypatch):
    monkeypatch.setattr(importer, "DATA_DIR", tmp_path)
    monkeypatch.setattr(importer, "load_group_map", lambda: {"a1": 1, "b2": 2})
    monkeypatch.setattr(importer, "load_teacher_map", lambda: {})
    client = Mock()
    monkeypatch.setattr(importer.RedisClientManager, "get_client", lambda _: client)
    (tmp_path / "groups_from_google_test.txt").write_text("A1\nB2\n", encoding="utf-8")
    csv = tmp_path / "schedule_from_google_test.csv"
    csv.write_text("group,date,lesson_number\nA1,2026-09-27,1\nB2,2026-09-27,2\n", encoding="utf-8")
    return csv, client


def event(caplog, name):
    return next(r for r in caplog.records if getattr(r, "event", None) == name)


def test_success_is_logged_after_data_is_saved(source, caplog):
    caplog.set_level(logging.INFO)
    _, client = source
    def check_write(*args, **kwargs):
        assert not any(getattr(r, "event", "") == "schedule.import.completed" for r in caplog.records)
    client.set.side_effect = check_write
    result = importer.process_google_schedule.run()
    record = event(caplog, "schedule.import.completed")
    assert result["status"] == record.outcome == "success"
    assert (record.rows_count, record.lessons_count, record.groups_count) == (2, 2, 2)
    assert record.duration_ms >= 0
    assert client.set.call_count == 5


def test_partial_import_counts_all_rows_and_bounds_private_diagnostics(source, caplog):
    caplog.set_level(logging.DEBUG, logger=importer.__name__)
    csv, client = source
    csv.write_text("group,date,lesson_number,raw_cell\nA1,2026-09-27,1,private-cell\n"
                   "B2,2026-09-27,secret-invalid-number,private-cell\n" +
                   "private-unknown-group,2026-09-27,1,private-cell\n" * 20, encoding="utf-8")
    result = importer.process_google_schedule.run()
    record = event(caplog, "schedule.import.completed")
    assert result["status"] == record.outcome == "partial"
    assert record.levelno == logging.WARNING
    assert (record.rows_count, record.lessons_count, record.groups_count, record.failed_count) == (22, 1, 1, 1)
    assert record.skipped_count == 20 and record.invalid_count == 1
    assert len([r for r in caplog.records if getattr(r, "event", "") == "schedule.import.row_skipped"]) == 10
    assert "private-" not in caplog.text and "secret-" not in caplog.text
    values = {call.args[0]: orjson.loads(call.args[1]) for call in client.set.call_args_list
              if call.args[0] != KeyEnum.MAIN_PAGE_HASH}
    assert values[KeyEnum.SCRAPED_GROUPS] == {"1": ""}
    assert len(values[KeyEnum.SCRAPED_LESSONS]) == 1
    assert values[KeyEnum.SCRAPY_SUMMARY]["closing_reason"] == "google_sheets_finished_partial"


@pytest.mark.parametrize("body,reason", [
    ("", "invalid_csv_header"),
    ("unexpected,secret-header\n1,2\n", "invalid_csv_header"),
    ("group,date,lesson_number\nA1,2026-09-27,secret\nB2,2026-09-27,secret\n", "no_valid_groups"),
])
def test_bad_import_fails_without_saving_lessons(source, caplog, body, reason):
    csv, client = source
    csv.write_text(body, encoding="utf-8")
    with pytest.raises(importer.GoogleScheduleError, match=reason):
        importer.process_google_schedule.run()
    record = event(caplog, "schedule.import.failed")
    assert record.reason == reason and record.outcome == "failed"
    assert [call.args[0] for call in client.set.call_args_list] == [KeyEnum.SCRAPY_SUMMARY]
    assert "secret" not in caplog.text


def test_redis_failure_never_claims_success_and_keeps_original_error(source, caplog):
    _, client = source
    error = RuntimeError("secret-redis-credentials")
    client.set.side_effect = error
    with pytest.raises(RuntimeError) as raised:
        importer.process_google_schedule.run()
    assert raised.value is error
    assert event(caplog, "schedule.import.failed").stage == "save_redis"
    assert event(caplog, "schedule.import.report_failed")
    assert not any(getattr(r, "event", "") == "schedule.import.completed" for r in caplog.records)
    assert "secret-redis" not in caplog.text


def test_missing_file_stops_celery_chain_before_sync(source, monkeypatch):
    csv, _ = source
    csv.unlink()
    downstream = Mock()
    monkeypatch.setattr(sync_lessons, "run", downstream)
    with pytest.raises(importer.GoogleScheduleError, match="lessons_file_missing"):
        chain(importer.process_google_schedule.s(), sync_lessons.s()).apply()
    downstream.assert_not_called()


def test_malformed_row_does_not_inherit_previous_group(source):
    csv, _ = source
    # An absent group value used to throw before assigning group_id, marking
    # the previous valid row's group as failed.
    csv.write_text("date,lesson_number,group\n2026-09-27,1,A1\n2026-09-27,2\n", encoding="utf-8")
    stats = {}
    lessons, failed = importer.process_lessons_csv(csv, {"a1": 1}, {}, stats=stats)
    assert len(lessons) == 1 and not failed
    assert stats["invalid_count"] == 1
