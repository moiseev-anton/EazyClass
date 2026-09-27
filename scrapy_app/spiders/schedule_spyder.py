from datetime import timedelta
import logging
from time import perf_counter
from urllib.parse import urljoin

import orjson
import scrapy
from asgiref.sync import sync_to_async
from django.conf import settings
from scrapy.exceptions import CloseSpider

from eazyclass.logging_config import safe_error_context

from scheduler.dtos.lesson_sync_range import LessonSyncRange
from scheduler.models import Group
from scrapy_app.response_processor import ResponseProcessor
from utils import RedisClientManager
from enums import KeyEnum

MAIN_PAGE_HASH_TTL = timedelta(days=3)


class ScheduleSpider(scrapy.Spider):
    """Класс паука для парсинга расписания с сайта."""

    name = "schedule_spider"
    base_url = settings.BASE_SCRAPING_URL

    def __init__(self, *args, cache_scope: str | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._started = perf_counter()
        self.scrape_failed = False
        try:
            self.redis_client = RedisClientManager.get_client("scrapy")
        except Exception as e:
            self.logger.error("Сбор расписания не начат: Redis недоступен", extra={"event": "schedule.scrape.failed", "reason": "redis_unavailable", **safe_error_context(e)})
            raise CloseSpider("Redis client initialization failed")

        self.cache_scope = cache_scope or LessonSyncRange.from_offsets().cache_scope
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
        self.logger.info("Начинается сбор расписания с сайта", extra={"event": "schedule.scrape.started"})

        # Сначала запрашиваем главную страницу
        yield scrapy.Request(
            url=main_page_url,
            callback=self.prepare_group_requests,
            errback=self._hangle_main_page_error,
        )

    async def prepare_group_requests(self, response: scrapy.http.Response):
        self.logger.debug("Главная страница получена")

        try:
            processor = ResponseProcessor(response, self.redis_client, cache_scope=self.cache_scope)
            processor.validate_page()
            self.main_page_hash = processor.get_content_hash()
            self.logger.debug("Структура главной страницы проверена")
        except Exception as e:
            self.logger.error("Структура главной страницы не распознана", extra={"event": "schedule.scrape.main_page_failed", "reason": "invalid_page", **safe_error_context(e)})
            raise CloseSpider("Main page validation failed")

        try:
            # Получаем список кортежей ("group_id", "endpoint")
            group_endpoints = await sync_to_async(Group.objects.get_endpoint_map)()
            # group_endpoints = [("5", "view.php?id=00312")]
        except Exception as e:
            error_msg = f"Ошибка при получении групп из БД"
            self.logger.error(error_msg, extra={"event": "schedule.scrape.groups_failed", **safe_error_context(e)})
            raise CloseSpider(error_msg)

        if not group_endpoints:
            raise CloseSpider("Нет групп для парсинга")

        remaining_groups = self._separate_groups(group_endpoints)

        self.summary["total_groups"] = len(group_endpoints)
        self.summary["skipped"] = len(group_endpoints) - len(remaining_groups)
        self.logger.debug("Запланировано обработать %s групп", len(remaining_groups))

        for group_id, endpoint in remaining_groups:
            url = urljoin(self.base_url, endpoint.lstrip("/"))
            self.logger.debug("Запланирован запрос страницы группы", extra={"group_id": group_id})
            yield scrapy.Request(
                url=url,
                callback=self.process_lessons_page,
                errback=self._handle_page_error,
                meta={"group_id": group_id},
            )

    def process_lessons_page(self, response: scrapy.http.Response):
        """Обрабатывает страницу расписания, проверяет изменения контента и извлекает данные о занятиях."""

        group_id = response.meta.get("group_id")
        self.logger.debug("Страница группы получена", extra={"group_id": group_id})
        try:
            processor = ResponseProcessor(response, self.redis_client, cache_scope=self.cache_scope)

            if not processor.is_content_changed():
                self.logger.debug("Расписание группы не изменилось", extra={"group_id": group_id})
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
            self.logger.warning("Не удалось обработать расписание группы", extra={"event": "schedule.scrape.group_failed", "group_id": group_id, **safe_error_context(e)})
            self.summary["errors"] += 1
            self.summary["error_groups"].append(group_id)

    def _hangle_main_page_error(self, failure):
        """Errback для главной страницы"""
        self.logger.error("Главная страница расписания недоступна", extra={"event": "schedule.scrape.main_page_failed", "reason": "request_failed", **safe_error_context(failure.value)})
        raise CloseSpider("Главная страница недоступна")

    def _handle_page_error(self, failure):
        """Errback для отдельных страниц — логируем и игнорируем, паук продолжается."""
        group_id = failure.request.meta.get("group_id", "unknown")
        self.logger.warning("Не удалось загрузить страницу группы", extra={"event": "schedule.scrape.group_failed", "group_id": group_id, **safe_error_context(failure.value)})
        self.summary["errors"] += 1
        self.summary["error_groups"].append(group_id)

    def closed(self, reason):
        """
        Метод, вызываемый при завершении работы паука. Сохраняет собранные данные в Redis.

        :param reason: Причина завершения работы паука.
        """
        try:
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

            self._log_summary(reason)
        except Exception as e:
            self.scrape_failed = True
            self.logger.error("Собранное расписание не удалось полностью сохранить в Redis", extra={"event": "schedule.scrape.save_failed", "outcome": "failed", **safe_error_context(e)})
            # Runner checks scrape_failed after shutdown. Scrapy swallows errors
            # from closed() and would otherwise log the raw exception again.

    def _log_summary(self, reason):
        summary = self.summary
        pending = max(0, summary["total_groups"] - sum(
            summary[key] for key in ("parsed", "skipped", "no_change", "errors")
        ))
        if reason == "Нет групп для парсинга":
            outcome, title, level = "skipped", "Сбор пропущен: нет групп", logging.INFO
        elif reason != "finished" or not summary["total_groups"]:
            outcome, title, level = "failed", "Сбор расписания остановлен до завершения", logging.ERROR
        elif summary["errors"] or pending:
            if summary["parsed"] + summary["skipped"] + summary["no_change"]:
                outcome, title, level = "partial", "Расписание собрано не полностью", logging.WARNING
            else:
                outcome, title, level = "failed", "Не удалось собрать расписание ни одной группы", logging.ERROR
        else:
            outcome, title, level = "success", "Сбор расписания завершён", logging.INFO
        self.scrape_failed = outcome == "failed"
        self.logger.log(
            level,
            "%s: разобрано групп %s, без изменений %s, ранее обработано %s, ошибок %s, не обработано %s; занятий %s",
            title, summary["parsed"], summary["no_change"], summary["skipped"],
            summary["errors"], pending, len(self.lessons),
            extra={"event": "schedule.scrape.completed", "outcome": outcome,
                   "groups_count": summary["total_groups"], "parsed_count": summary["parsed"],
                   "unchanged_count": summary["no_change"], "skipped_count": summary["skipped"],
                   "failed_count": summary["errors"], "pending_count": pending,
                   "lessons_count": len(self.lessons),
                   "duration_ms": round((perf_counter() - self._started) * 1000, 3)},
        )

    def _separate_groups(self, group_endpoints):
        # Получаем хеш главной страницы и проверяем синхронизированные группы
        set_key = f"{KeyEnum.SYNCED_GROUPS_PREFIX}{self.cache_scope}{self.main_page_hash}"
        synced_groups = self.redis_client.smembers(set_key)
        self.logger.debug("В кеше отмечено %s обработанных групп", len(synced_groups))

        return [
            (group_id, endpoint)
            for group_id, endpoint in group_endpoints
            if group_id not in synced_groups
        ]
