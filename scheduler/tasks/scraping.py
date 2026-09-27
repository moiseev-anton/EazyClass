import logging

from billiard.context import Process
from celery import shared_task
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from eazyclass.logging_config import configure_service_logging
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
            self._crawl_with_logging()

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
        process.crawl(self.spider_cls, **self.spider_kwargs)
        process.start()

    def run(self):
        """Запуск отдельного процесса для работы паука."""
        process = Process(target=self._crawl, args=(get_context(),))
        process.start()
        process.join()


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def run_schedule_spider(self, cache_scope: str | None = None):
    try:
        runner = SpiderRunner(ScheduleSpider, cache_scope=cache_scope)
        runner.run()
    except Exception as e:
        logger.error(f"Ошибка при запуске паука: {e}")
        raise
