import hashlib
import json
from urllib.parse import urljoin

import scrapy
from django.conf import settings

from scheduler.models import Group  # Импорт модели Group
from scrapy_app.eazy_scrapy.schedule_page_parser import SchedulePageParser
from utils.redis_clients import get_scrapy_redis_client

SCRAPED_LESSONS_KEY = "scrapy:scraped_lesson_items"
SCRAPED_GROUPS_KEY = "scrapy:scraped_group_ids"
PAGE_HASH_KEY_PREFIX = 'scrapy:last_content_hash:group_id:'


class ScheduleSpider(scrapy.Spider):
    name = 'schedule_spider'
    base_url = settings.BASE_SCRAPING_URL

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis_client = get_scrapy_redis_client()
        self.lessons = []
        self.scraped_groups = dict()

    def start_requests(self):
        # Получаем список групп и ссылок из БД
        group_links = Group.objects.link_map()  # Получаем список кортежей (group_id, link)

        # Проходим по всем ссылкам и отправляем запросы
        for group_id, link in group_links:
            url = urljoin(self.base_url, link)
            yield scrapy.Request(url=url, callback=self.process_page, meta={'group_id': group_id})

    def process_page(self, response):
        try:
            group_id = response.meta['group_id']
            current_content_hash = hashlib.md5(response.body).hexdigest()
            # TODO: реализовать проверку прошлого хеша
            parser = SchedulePageParser(response)
            lessons = parser.parse()
            self.lessons.extend(lessons)
            self.scraped_groups[group_id] = current_content_hash
        except Exception as e:
            self.logger.error(f"Ошибка обработки страницы: {e}")

    def closed(self, reason):
        # Этот метод вызывается при завершении работы паука
        if self.scraped_groups:
            # Преобразуем список уроков в JSON
            lessons_json = json.dumps(self.lessons)
            group_ids_json = json.dumps(self.scraped_groups)

            # Помещаем данные в Redis
            self.redis_client.set(SCRAPED_LESSONS_KEY, lessons_json)
            self.redis_client.set(SCRAPED_GROUPS_KEY, group_ids_json)

        self.logger.info("Паук завершен. Данные сохранены в Redis.")
