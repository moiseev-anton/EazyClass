from concurrent.futures import ThreadPoolExecutor
import io
import json
import logging
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID, uuid4

from celery import Celery, chain
from celery.contrib.testing.worker import start_worker
from django.http import HttpResponse
from django.test import RequestFactory
import pytest

from eazyclass.logging_config import EventFormatter
from eazyclass.logging_context import (
    ContextFilter, REQUEST_HEADER, RUN_HEADER, get_context, logging_context,
    publish_context,
)
from scheduler.middleware import RequestLoggingMiddleware


@pytest.fixture
def captured_logs():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(EventFormatter(style="json"))
    handler.addFilter(ContextFilter())
    root = logging.getLogger()
    root.addHandler(handler)
    old_level = root.level
    root.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
        handler.close()


def test_http_response_and_inner_logs_share_id_and_context_is_cleared(captured_logs):
    def view(request):
        request.resolver_match = SimpleNamespace(route="api/items/<int:pk>/")
        logging.getLogger("scheduler.test").info("Внутри запроса")
        assert get_context() == {"request_id": request.request_id}
        return HttpResponse(status=404)

    middleware = RequestLoggingMiddleware(view)
    responses = [middleware(RequestFactory().get(
        "/api/items/3/?nonce=secret-nonce", HTTP_X_REQUEST_ID="secret-client-id",
    )) for _ in range(2)]
    ids = [response["X-Request-ID"] for response in responses]
    assert ids[0] != ids[1]
    assert all(str(UUID(value)) == value for value in ids)
    assert get_context() == {}
    records = captured_logs()
    for request_id in ids:
        matching = [record for record in records if record.get("request_id") == request_id]
        assert len(matching) == 2
        assert matching[-1]["status_code"] == 404
        assert matching[-1]["duration_ms"] >= 0
    assert "secret-" not in json.dumps(records)


def test_http_exception_logs_location_and_restores_outer_context(captured_logs):
    def failing_view(request):
        raise RuntimeError("secret-exception")

    with logging_context({"run_id": "outer-operation"}):
        with pytest.raises(RuntimeError):
            RequestLoggingMiddleware(failing_view)(RequestFactory().get("/"))
        assert get_context() == {"run_id": "outer-operation"}
    record = captured_logs()[-1]
    assert record["status_code"] == 500
    assert record["error_type"] == "RuntimeError"
    assert "run_id" not in record
    assert "secret-exception" not in json.dumps(record)
    assert get_context() == {}


def test_context_is_isolated_between_threads():
    from threading import Barrier
    barrier = Barrier(2)

    def run(value):
        with logging_context({"request_id": value}):
            barrier.wait(timeout=5)
            return get_context()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run, value) for value in ("first", "second")]
        assert [f.result() for f in futures] == [{"request_id": "first"}, {"request_id": "second"}]
    assert get_context() == {}


def test_publication_only_transports_correlation_not_task_or_user_data():
    request_id, run_id = str(uuid4()), str(uuid4())
    with logging_context({"request_id": request_id, "run_id": run_id,
                          "task_id": str(uuid4()), "attempt": 7, "user_id": 42}):
        headers = {"id": str(uuid4()), REQUEST_HEADER: "invalid\nsecret"}
        publish_context(headers=headers)
    assert headers[REQUEST_HEADER] == request_id
    assert headers[RUN_HEADER] == run_id
    assert set(headers) == {"id", REQUEST_HEADER, RUN_HEADER}


def test_real_worker_chain_retry_and_next_task_keep_correct_context(settings):
    # In-memory broker/backend: exercise actual publication, worker signals,
    # chain continuation and retry without Redis or the project's scheduled jobs.
    # Valid signal configuration, without replacing pytest's own handlers.
    settings.LOGGING = {"version": 1, "disable_existing_loggers": False}
    app = Celery("logging-context-tests", broker="memory://",
                 backend="cache+memory://", set_as_current=False)
    app.conf.update(task_default_queue="logging-context-tests", task_serializer="json",
                    accept_content=["json"], result_serializer="json")
    attempts = []

    @app.task(bind=True)
    def first(self):
        return [get_context()]

    @app.task(bind=True, max_retries=1)
    def second(self, previous):
        attempts.append(get_context())
        if self.request.retries == 0:
            raise self.retry(countdown=0)
        return previous + [get_context()]

    @app.task
    def last(previous):
        return previous + [get_context()]

    @app.task
    def failing():
        raise ValueError("expected test failure")

    @app.task
    def unrelated():
        return get_context()

    request_id = str(uuid4())
    with start_worker(app, pool="solo", perform_ping_check=False, shutdown_timeout=10):
        with logging_context({"request_id": request_id}):
            result = chain(first.s(), second.s(), last.s()).apply_async()
        contexts = result.get(timeout=10, interval=0.05)
        assert len({c["run_id"] for c in contexts}) == 1
        assert len({c["task_id"] for c in contexts}) == 3
        assert all(c["request_id"] == request_id for c in contexts)
        assert contexts[0]["run_id"] == contexts[0]["task_id"]
        assert [c["attempt"] for c in attempts] == [1, 2]
        assert attempts[0]["task_id"] == attempts[1]["task_id"]
        assert attempts[0]["run_id"] == attempts[1]["run_id"] == contexts[0]["run_id"]
        with pytest.raises(ValueError):
            failing.delay().get(timeout=10, interval=0.05)
        clean = unrelated.delay().get(timeout=10, interval=0.05)
        assert "request_id" not in clean
        assert clean["run_id"] == clean["task_id"] != contexts[0]["run_id"]
        assert clean["attempt"] == 1
    app.close()
    assert get_context() == {}


def test_nested_eager_task_restores_parent_context():
    app = Celery("nested-context", broker="memory://", backend="cache+memory://", set_as_current=False)

    @app.task
    def child():
        return get_context()

    @app.task
    def parent():
        before = get_context()
        child_context = child.apply().get()
        assert get_context() == before
        return before, child_context

    outer, inner = parent.apply().get()
    assert outer["task_id"] != inner["task_id"]
    assert get_context() == {}
    app.close()


def test_spider_runner_transports_snapshot_and_restores_context(monkeypatch):
    from scheduler.tasks import scraping

    process_factory = Mock()
    monkeypatch.setattr(scraping, "Process", process_factory)
    runner = scraping.SpiderRunner(Mock())
    crawl = Mock(side_effect=lambda: get_context())
    monkeypatch.setattr(runner, "_crawl_with_logging", crawl)
    expected = {"request_id": str(uuid4()), "run_id": str(uuid4()),
                "task_id": str(uuid4()), "attempt": 2}
    with logging_context(expected):
        runner.run()
    snapshot = process_factory.call_args.kwargs["args"][0]
    assert snapshot == expected
    observed = []
    crawl.side_effect = lambda: observed.append(get_context())
    runner._crawl(snapshot)
    assert observed == [expected]
    assert get_context() == {}
    crawl.side_effect = RuntimeError("failed to start spider")
    with pytest.raises(RuntimeError):
        runner._crawl(snapshot)
    assert get_context() == {}
