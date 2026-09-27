import logging
from unittest.mock import Mock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError
from scrapy.http import HtmlResponse, Request

from eazyclass.logging_config import CeleryEventFilter, EventFormatter
from scheduler.tasks import scraping, synchronisation
from scrapy_app.spiders import schedule_spyder


@pytest.fixture
def spider(monkeypatch):
    monkeypatch.setattr(schedule_spyder.RedisClientManager, "get_client", lambda _: Mock())
    return schedule_spyder.ScheduleSpider()


@pytest.mark.parametrize("errors,pending,reason,outcome,level", [
    (0, 0, "finished", "success", logging.INFO),
    (1, 0, "finished", "partial", logging.WARNING),
    (0, 1, "finished", "partial", logging.WARNING),
    (0, 0, "shutdown", "failed", logging.ERROR),
    (0, 0, "Нет групп для парсинга", "skipped", logging.INFO),
])
def test_spider_summary_reports_coverage_after_storage(spider, caplog, errors, pending, reason, outcome, level):
    caplog.set_level(logging.INFO)
    spider.summary.update(total_groups=3 + errors + pending, parsed=1, no_change=1, skipped=1, errors=errors)
    spider.closed(reason)
    record = next(r for r in caplog.records if getattr(r, "event", None) == "schedule.scrape.completed")
    assert record.outcome == outcome and record.levelno == level
    assert record.pending_count == pending and record.failed_count == errors
    assert record.parsed_count + record.unchanged_count + record.skipped_count + errors + pending == record.groups_count
    assert spider.redis_client.set.call_count == 4


def test_storage_error_does_not_log_completion(spider, caplog):
    caplog.set_level(logging.INFO)
    spider.redis_client.set.side_effect = RuntimeError("secret-redis-url")
    spider.closed("finished")
    assert not any(getattr(r, "event", None) == "schedule.scrape.completed" for r in caplog.records)
    assert "secret-redis-url" not in caplog.text
    assert spider.scrape_failed


def test_all_groups_failed_is_failure_not_partial(spider, caplog):
    spider.summary.update(total_groups=2, errors=2)
    spider.closed("finished")
    assert spider.scrape_failed
    assert any(getattr(r, "outcome", None) == "failed" for r in caplog.records)


def test_runner_checks_failures_that_scrapy_does_not_raise(monkeypatch):
    from twisted.internet.defer import succeed, fail
    monkeypatch.setattr(scraping, "configure_service_logging", Mock())
    monkeypatch.setattr(scraping, "get_project_settings", lambda: {})
    process = Mock()
    process.create_crawler.return_value.spider.scrape_failed = True
    process.crawl.return_value = succeed(None)
    monkeypatch.setattr(scraping, "CrawlerProcess", Mock(return_value=process))
    with pytest.raises(RuntimeError, match="Schedule collection failed"):
        scraping.SpiderRunner(Mock())._crawl_with_logging()
    process.create_crawler.return_value.spider.scrape_failed = False
    process.crawl.return_value = fail(RuntimeError("startup failed"))
    with pytest.raises(RuntimeError, match="Spider execution failed"):
        scraping.SpiderRunner(Mock())._crawl_with_logging()


def test_cache_error_is_not_reported_as_unchanged_group(spider, caplog):
    caplog.set_level(logging.INFO)
    spider.redis_client.get.side_effect = RedisConnectionError("secret-redis-url")
    response = HtmlResponse("https://example.invalid/view", body=b"<html></html>",
                            request=Request("https://example.invalid/view", meta={"group_id": "42"}))
    spider.process_lessons_page(response)
    assert spider.summary["errors"] == 1
    assert spider.summary["no_change"] == 0 and not spider.unchanged_groups
    record = next(r for r in caplog.records if getattr(r, "event", None) == "schedule.scrape.group_failed")
    assert record.group_id == "42"
    assert "secret-redis-url" not in caplog.text


@pytest.mark.parametrize("retries,event,level", [(0, "schedule.sync.retry_requested", logging.WARNING),
                                               (2, "schedule.sync.failed", logging.ERROR)])
def test_sync_report_failure_does_not_claim_success(monkeypatch, caplog, retries, event, level):
    caplog.set_level(logging.INFO)
    client = Mock()
    client.get.side_effect = RuntimeError("secret-payload")
    monkeypatch.setattr(synchronisation.RedisClientManager, "get_client", lambda _: client)
    monkeypatch.setattr(synchronisation, "LessonsSyncManager", Mock(return_value=Mock(
        update_schedule=Mock(return_value={"added": [], "updated": [], "removed": []}))))
    monkeypatch.setattr(synchronisation.sync_lessons, "retry", Mock(side_effect=RuntimeError("retry")))
    synchronisation.sync_lessons.push_request(retries=retries)
    try:
        with pytest.raises(RuntimeError):
            synchronisation.sync_lessons.run()
    finally:
        synchronisation.sync_lessons.pop_request()
    records = [r for r in caplog.records if getattr(r, "event", None) == event]
    assert len(records) == 1 and records[0].levelno == level
    assert records[0].stage == "build_report"
    assert not any(getattr(r, "event", None) == "schedule.sync.completed" for r in caplog.records)
    assert "secret-payload" not in caplog.text


def test_sync_completion_contains_change_counts(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    client = Mock()
    client.get.return_value = b"{}"
    monkeypatch.setattr(synchronisation.RedisClientManager, "get_client", lambda _: client)
    monkeypatch.setattr(synchronisation, "LessonsSyncManager", Mock(return_value=Mock(
        update_schedule=Mock(return_value={"added": [{}, {}], "updated": [{}], "removed": []}))))
    result = synchronisation.sync_lessons.run()
    record = next(r for r in caplog.records if getattr(r, "event", None) == "schedule.sync.completed")
    assert (record.added_count, record.updated_count, record.removed_count) == (2, 1, 0)
    assert record.duration_ms >= 0
    assert result["sync_summary"]["added"] == [{}, {}]


def test_spider_subprocess_failure_propagates(monkeypatch):
    monkeypatch.setattr(scraping, "Process", Mock(return_value=Mock(exitcode=1)))
    with pytest.raises(RuntimeError, match="Spider subprocess failed"):
        scraping.SpiderRunner(Mock()).run()


@pytest.mark.parametrize("level,visible", [(logging.INFO, False), (logging.DEBUG, True)])
def test_celery_routine_messages_are_debug_without_result_payload(caplog, level, visible):
    from celery.app.trace import LOG_SUCCESS
    caplog.set_level(level, logger="scheduler")
    payload = {"id": "task-id", "name": "scheduler.task", "runtime": 1, "return_value": "secret-result"}
    record = logging.LogRecord("celery.app.trace", logging.INFO, __file__, 1, LOG_SUCCESS, (payload,), None)
    record.data = payload
    assert CeleryEventFilter().filter(record) is visible
    if visible:
        assert record.levelno == logging.DEBUG
        assert record.task_id == "task-id"
        for style in ("text", "text_verbose", "json"):
            assert "secret-result" not in EventFormatter(style=style).format(record)


def test_celery_error_does_not_print_raw_exception_or_arguments():
    from celery.app.trace import LOG_FAILURE
    payload = {"id": "task-id", "name": "scheduler.task", "description": "failed",
               "exc": "secret-error", "args": "secret-args"}
    record = logging.LogRecord("celery.app.trace", logging.ERROR, __file__, 1, LOG_FAILURE, (payload,), None)
    record.data = payload
    assert CeleryEventFilter().filter(record)
    assert record.levelno == logging.ERROR
    assert "secret-" not in EventFormatter(style="json").format(record)
