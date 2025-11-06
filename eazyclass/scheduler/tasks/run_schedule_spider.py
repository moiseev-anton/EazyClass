import logging

from billiard.context import Process
from celery import shared_task
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from scrapy_app.spiders import ScheduleSpider

logger = logging.getLogger(__name__)


class SpiderRunner:
    """Класс для запуска Scrapy паука в отдельном процессе."""

    def __init__(self, spider_cls, **spider_kwargs):
        self.spider_cls = spider_cls
        self.spider_kwargs = spider_kwargs

    def _crawl(self):
        """Запуск паука."""
        process = CrawlerProcess(get_project_settings())
        process.crawl(self.spider_cls, **self.spider_kwargs)
        process.start()

    def run(self):
        """Запуск отдельного процесса для работы паука."""
        process = Process(target=self._crawl)
        process.start()
        process.join()


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue="periodic_tasks")
def run_schedule_spider(self):
    logger.info("Запуск задачи ...")

    try:
        runner = SpiderRunner(ScheduleSpider)
        runner.run()
        logger.info("Завершение задачи ...")
    except Exception as e:
        logger.error(f"Ошибка при запуске паука: {e}")
