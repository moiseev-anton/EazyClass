import orjson
from urllib.parse import urljoin

import scrapy
from asgiref.sync import sync_to_async
from django.conf import settings

from scheduler.models import Group
from scrapy_app.response_processor import ResponseProcessor
from utils import RedisClientManager, KeyEnum

from scrapy.exceptions import CloseSpider


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
            raise CloseSpider("Redis client initialization failed")

        self.lessons = []
        self.scraped_groups = {}
        self.summary = {
            'total_groups': 0,
            'changed': 0,
            'no_change': 0,
            'errors': 0,
            'error_groups': [],
            'total_lessons': 0
        }


    async def start(self):
        try:
            # Получаем список кортежей ("group_id", "endpoint")
            group_endpoints = await sync_to_async(Group.objects.get_endpoint_map)()
            # group_endpoints = [("5", "view.php?id=00312")]
        except Exception as e:
            error_msg = f"Ошибка при обращении к БД (Group.objects.get_endpoint_map): {e}"
            self.logger.exception(error_msg)  # logger.exception покажет полный traceback
            raise scrapy.exceptions.CloseSpider(error_msg)

        # Проходим по всем ссылкам и отправляем запросы
        if not group_endpoints:
            raise CloseSpider("Нет групп для парсинга")

        self.summary['total_groups'] = len(group_endpoints)
        self.logger.info(f"Запланировано обработать {len(group_endpoints)} групп")

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

        group_id = response.meta.get('group_id')
        self.logger.info(f"Получен ответ от :{response.url}(group_id:{group_id})")
        try:
            processor = ResponseProcessor(response, self.redis_client)

            if not processor.is_content_changed():
                self.logger.info(f"Содержимое страницы группы:{group_id} не изменилось")
                self.summary['no_change'] += 1
                return

            if extracted_lessons := processor.extract_lessons():
                self.lessons.extend(extracted_lessons)
                self.summary['total_lessons'] += len(extracted_lessons)

            content_hash = processor.get_content_hash()
            self.scraped_groups[str(group_id)] = content_hash
            self.summary['changed'] += 1
            self.scraped_groups[group_id] = content_hash

        except Exception as e:
            self.logger.error(f"Ошибка обработки страницы (group_id: {group_id}): {e}")
            self.summary['errors'] += 1
            self.summary['error_groups'].append(group_id)


    def closed(self, reason):
        """
        Метод, вызываемый при завершении работы паука. Сохраняет собранные данные в Redis.

        :param reason: Причина завершения работы паука.
        """
        try:
            self.logger.info(f"Начинается закрытие паука. Причина: {reason}")

            lessons_json = orjson.dumps(self.lessons)
            group_ids_json = orjson.dumps(self.scraped_groups)
            summary_json = orjson.dumps(self.summary)

            # Помещаем данные в Redis
            self.redis_client.set(KeyEnum.SCRAPED_LESSONS, lessons_json)
            self.redis_client.set(KeyEnum.SCRAPED_GROUPS, group_ids_json)
            self.redis_client.set(KeyEnum.SCRAPY_SUMMARY, summary_json)

            self.logger.info(f"Сохранено {len(self.lessons)} уроков для {len(self.scraped_groups)} групп в Redis.")
            self.logger.info(f"Сохранен summary: {self.summary}")
            self.logger.info(f'Паук {self.name} закрыт.')
        except Exception as e:
            self.logger.error(f"Ошибка при закрытии паука: {e}")
            raise


