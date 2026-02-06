from datetime import timedelta
from urllib.parse import urljoin

import orjson
import scrapy
from asgiref.sync import sync_to_async
from django.conf import settings
from scrapy.exceptions import CloseSpider

from scheduler.models import Group
from scrapy_app.response_processor import ResponseProcessor
from utils import KeyEnum, RedisClientManager

MAIN_PAGE_HASH_TTL = timedelta(days=3)


class ScheduleSpider(scrapy.Spider):
    """Класс паука для парсинга расписания с сайта."""

    name = "schedule_spider"
    base_url = settings.BASE_SCRAPING_URL

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.redis_client = RedisClientManager.get_client("scrapy")
        except Exception as e:
            self.logger.error(f"Не удалось получить Redis клиент: {e}")
            raise CloseSpider("Redis client initialization failed")

        self.lessons = []
        self.scraped_groups = {}
        self.unchanged_groups = set()
        self.main_page_hash = None
        self.summary = {
            "total_groups": 0,
            "parsed": 0,
            "skipped": 0,
            "no_change": 0,
            "errors": 0,
            "error_groups": [],
            "total_lessons": 0,
            "closing_reason": None,
        }

    async def start(self):
        main_page_url = urljoin(self.base_url, "view.php")
        self.logger.info(f"Проверка доступности главной страницы → {main_page_url}")

        # Сначала запрашиваем главную страницу
        yield scrapy.Request(
            url=main_page_url,
            callback=self.prepare_group_requests,
            errback=self._hangle_main_page_error,
        )

    async def prepare_group_requests(self, response: scrapy.http.Response):
        self.logger.info(f"Главная страница получена: {response.url}")

        try:
            processor = ResponseProcessor(response, self.redis_client)
            processor.validate_page()
            self.main_page_hash = processor.get_content_hash()
            self.logger.info(f"Валидация главной страницы прошла успешно. Хеш: {self.main_page_hash}")
        except Exception as e:
            self.logger.error(f"Ошибка валидации главной страницы: {e}")
            raise CloseSpider("Main page validation failed")

        try:
            # Получаем список кортежей ("group_id", "endpoint")
            group_endpoints = await sync_to_async(Group.objects.get_endpoint_map)()
            # group_endpoints = [("5", "view.php?id=00312")]
        except Exception as e:
            error_msg = f"Ошибка при получении групп из БД"
            self.logger.exception(f"{error_msg}: {e}")  # logger.exception покажет полный traceback
            raise CloseSpider(error_msg)

        if not group_endpoints:
            raise CloseSpider("Нет групп для парсинга")

        remaining_groups = self._separate_groups(group_endpoints)

        self.summary["total_groups"] = len(group_endpoints)
        self.summary["skipped"] = len(group_endpoints) - len(remaining_groups)
        self.logger.info(f"Запланировано обработать {len(remaining_groups)} групп")

        for group_id, endpoint in remaining_groups:
            url = urljoin(self.base_url, endpoint.lstrip("/"))
            self.logger.info(f"Запланирован запрос → {url} (group:{group_id})")
            yield scrapy.Request(
                url=url,
                callback=self.process_lessons_page,
                errback=self._handle_page_error,
                meta={"group_id": group_id},
            )

    def process_lessons_page(self, response: scrapy.http.Response):
        """Обрабатывает страницу расписания, проверяет изменения контента и извлекает данные о занятиях."""

        group_id = response.meta.get("group_id")
        self.logger.info(f"Получен ответ от :{response.url}(group_id:{group_id})")
        try:
            processor = ResponseProcessor(response, self.redis_client)

            if not processor.is_content_changed():
                self.logger.info(f"Содержимое страницы группы:{group_id} не изменилось")
                self.summary["no_change"] += 1
                self.unchanged_groups.add(group_id)
                return

            if extracted_lessons := processor.extract_lessons():
                self.lessons.extend(extracted_lessons)
                self.summary["total_lessons"] += len(extracted_lessons)

            content_hash = processor.get_content_hash()
            self.scraped_groups[group_id] = content_hash
            self.summary["parsed"] += 1

        except Exception as e:
            self.logger.error(f"Ошибка обработки страницы (group_id: {group_id}): {e}")
            self.summary["errors"] += 1
            self.summary["error_groups"].append(group_id)

    def _hangle_main_page_error(self, failure):
        """Errback для главной страницы"""
        self.logger.error(f"Ошибка при запросе главной страницы: {failure}")
        raise CloseSpider("Главная страница недоступна")

    def _handle_page_error(self, failure):
        """Errback для отдельных страниц — логируем и игнорируем, паук продолжается."""
        group_id = failure.request.meta.get("group_id", "unknown")
        self.logger.warning(f"Ошибка обработки страницы группы {group_id}: {failure.value}")
        self.summary["errors"] += 1
        self.summary["error_groups"].append(group_id)

    def closed(self, reason):
        """
        Метод, вызываемый при завершении работы паука. Сохраняет собранные данные в Redis.

        :param reason: Причина завершения работы паука.
        """
        try:
            self.logger.info(f"Начинается закрытие паука. Причина: {reason}")
            self.summary["closing_reason"] = reason

            lessons_json = orjson.dumps(self.lessons)
            group_ids_json = orjson.dumps(self.scraped_groups)
            summary_json = orjson.dumps(self.summary)
            unchanged_json = orjson.dumps(list(self.unchanged_groups))

            # Помещаем данные в Redis
            self.redis_client.set(KeyEnum.SCRAPED_LESSONS, lessons_json)
            self.redis_client.set(KeyEnum.SCRAPED_GROUPS, group_ids_json)
            self.redis_client.set(KeyEnum.SCRAPY_SUMMARY, summary_json)
            self.redis_client.set(KeyEnum.UNCHANGED_GROUPS, unchanged_json)

            # сохраняем хеш главной страницы, если он был вычислен
            if self.main_page_hash:
                self.redis_client.set(
                    KeyEnum.MAIN_PAGE_HASH,
                    self.main_page_hash,
                    ex=MAIN_PAGE_HASH_TTL,  # 3 суток
                )
                self.logger.info(f"Сохранён last_version_main_page_hash={self.main_page_hash}")

            self.logger.info(f"Сохранено {len(self.lessons)} уроков для {len(self.scraped_groups)} групп в Redis.")
            self.logger.info(f"Сохранен summary: {self.summary}")
            self.logger.info(f"Сохранены unchanged_groups: {len(self.unchanged_groups)} групп")
            self.logger.info(f"Паук {self.name} закрыт.")
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии паука: {e}")
            raise

    def _separate_groups(self, group_endpoints):
        # Получаем хеш главной страницы и проверяем синхронизированные группы
        set_key = f"{KeyEnum.SYNCED_GROUPS_PREFIX}{self.main_page_hash}"
        synced_groups = self.redis_client.smembers(set_key)
        self.logger.info(f"synced_groups: {synced_groups}")

        return [
            (group_id, endpoint)
            for group_id, endpoint in group_endpoints
            if group_id not in synced_groups
        ]
