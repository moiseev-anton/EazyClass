import logging
import pickle
from typing import Any, Generator
import inspect
from asgiref.sync import sync_to_async
from urllib.parse import urljoin
from scrapy import signals

import scrapy
from django.conf import settings
from scrapy import Request

from scheduler.models import Group
from scrapy_app.response_processor import ResponseProcessor
from utils import RedisClientManager

NEW_MAIN_PAGE_HASH_KEY = "scrapy:new_hash_main_page"
PREVIOUS_MAIN_PAGE_HASH_KEY = "scrapy:previous_hash_main_page"
SCRAPED_LESSONS_KEY = "scrapy:scraped_lesson_items"
SCRAPED_GROUPS_KEY = "scrapy:scraped_group_ids"
PAGE_HASH_KEY_PREFIX = 'scrapy:content_hash:group_id:'


class ScheduleSpider(scrapy.Spider):
    """Класс паука для парсинга расписания с сайта."""
    name = 'schedule_spider'
    base_url = settings.BASE_SCRAPING_URL

    # TODO: Подумать над предварительным запросом к основной странице.
    #  Сверить хеш страницы с сохраненных хешем.
    #  Но сохранять такой хеш надо только после синхранизации данных с БД
    #  Можно после синхронизации сверить множество групп для которых произведена синзронизация и множество групп в БД
    #  Если есть разница множеств то не сохраняем хеш основной старницы
    #  иначе до следующего обновленя сайта не получим данные для неуспешно обработанных групп.
    #  Если разницу множеств использовать дальше не придется можем обойтись сравнением количества (без множеств)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.redis_client = RedisClientManager.get_client('scrapy')
        except Exception as e:
            self.logger.error(f"Не удалось получить Redis клиент: {e}")
            raise

        self.lessons = []
        self.scraped_groups = {}



    async def start(self):
        try:
            group_endpoints = await sync_to_async(Group.objects.get_endpoint_map)()  # Получаем список кортежей (group_id, endpoint)
        except Exception as e:
            self.logger.error(f"Ошибка при получении endpoints групп из БД: {e}", exc_info=True)
            raise
        # group_endpoints = [(5, 'view.php?id=00312')]

        # Проходим по всем ссылкам и отправляем запросы
        if not group_endpoints:
            self.logger.info("Список endpoint'ов пуст, запросы не будут отправлены")
            return

        for group_id, endpoint in group_endpoints:
            url = urljoin(self.base_url, endpoint.lstrip('/'))
            self.logger.info(f'Запланирован запрос → {url} (group:{group_id})')

            yield scrapy.Request(
                url=url,
                callback=self.process_page,
                meta={'group_id': group_id}
            )


    def process_page(self, response: scrapy.http.Response):
        """ Обрабатывает страницу расписания, проверяет изменения контента и извлекает данные о занятиях. """

        self.logger.info(f"Получен ответ от :{response.url}(group_id:{response.meta.get('group_id')})")
        try:
            processor = ResponseProcessor(response, self.redis_client)

            if not processor.is_content_changed():
                self.logger.info(f"Содержимое страницы группы:{response.meta.get('group_id')} не изменилось")
                return

            lessons = processor.extract_lessons()
            if lessons:
                self.lessons.extend(lessons)

            group_id, content_hash = processor.get_group_hash_pair()
            self.scraped_groups[group_id] = content_hash

        except Exception as e:
            self.logger.error(f"Ошибка обработки страницы: {e}")

    def closed(self, reason):
        """
        Метод, вызываемый при завершении работы паука. Сохраняет собранные данные в Redis.

        :param reason: Причина завершения работы паука.
        """
        try:
            self.logger.info(f"Начинается закрытие паука. Причина: {reason}")

            lessons_json = pickle.dumps(self.lessons)
            group_ids_json = pickle.dumps(self.scraped_groups)

            # Помещаем данные в Redis
            self.redis_client.set(SCRAPED_LESSONS_KEY, lessons_json)
            self.redis_client.set(SCRAPED_GROUPS_KEY, group_ids_json)

            self.logger.info(f"Сохранено {len(self.lessons)} уроков для {len(self.scraped_groups)} групп в Redis.")
            self.logger.info(f'Паук {self.name} закрыт.')
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии паука: {e}")
            raise


