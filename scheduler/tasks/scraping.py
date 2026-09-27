import logging

from billiard.context import Process
from celery import shared_task
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from eazyclass.logging_config import configure_service_logging, safe_error_context
from eazyclass.logging_context import get_context, logging_context

from scrapy_app.spiders import ScheduleSpider

logger = logging.getLogger(__name__)


class SpiderRunner:
    """Класс для запуска Scrapy паука в отдельном процессе."""

    def __init__(self, spider_cls, **spider_kwargs):
        self.spider_cls = spider_cls
        self.spider_kwargs = spider_kwargs

    def _crawl(self, context=None):
        # Explicit transport works without relying on fork inheritance.
        with logging_context(context or {}):
            try:
                self._crawl_with_logging()
            except Exception as exc:
                logger.error("Процесс сбора расписания завершился ошибкой",
                             extra={"event": "schedule.scrape.process_failed", **safe_error_context(exc)})
                # Billiard would otherwise print a raw exception chain to stderr.
                raise SystemExit(1) from None

    def _crawl_with_logging(self):
        """Запуск паука."""
        import os

        os.environ.setdefault(
            "SCRAPY_SETTINGS_MODULE",
            "scrapy_app.settings"
        )

        configure_service_logging(service="scrapy")
        process = CrawlerProcess(settings=get_project_settings(), install_root_handler=False)
        # Scrapy configures library levels even with install_root_handler=False.
        configure_service_logging(service="scrapy")
        crawler = process.create_crawler(self.spider_cls)
        failures = []
        deferred = process.crawl(crawler, **self.spider_kwargs)
        deferred.addErrback(failures.append)
        process.start()
        # Scrapy reports some failures through Deferred/signals, not process exit.
        if failures:
            raise RuntimeError("Spider execution failed") from failures[0].value
        if getattr(crawler.spider, "scrape_failed", False):
            raise RuntimeError("Schedule collection failed")

    def run(self):
        """Запуск отдельного процесса для работы паука."""
        process = Process(target=self._crawl, args=(get_context(),))
        process.start()
        process.join()
        if process.exitcode != 0:
            raise RuntimeError("Spider subprocess failed")


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def run_schedule_spider(self, cache_scope: str | None = None):
    try:
        runner = SpiderRunner(ScheduleSpider, cache_scope=cache_scope)
        runner.run()
    except Exception as e:
        logger.error("Не удалось выполнить сбор расписания в процессе паука",
                     extra={"event": "schedule.scrape.process_failed", **safe_error_context(e)})
        raise
