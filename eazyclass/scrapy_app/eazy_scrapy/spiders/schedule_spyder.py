import json
from urllib.parse import urljoin

import scrapy

from scheduler.models import Group  # Импорт модели Group
from scrapy_app.eazy_scrapy.item_loaders import LessonLoader
from scrapy_app.eazy_scrapy.items import LessonItem
from utils.redis_clients import get_scrapy_redis_client


class ScheduleSpider(scrapy.Spider):
    name = 'schedule_spider'
    base_url = 'https://bincol.ru/rasp/'
    allowed_domains = ['https://bincol.ru']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.redis_client = get_scrapy_redis_client()
        self.lessons = []
        self.scraped_group_ids = set()

    def start_requests(self):
        # Получаем список групп и ссылок из БД
        group_links = Group.objects.link_map()  # Получаем список кортежей (group_id, link)

        # Проходим по всем ссылкам и отправляем запросы
        for group_id, link in group_links:
            url = urljoin(self.base_url, link)
            yield scrapy.Request(url=url, callback=self.parse_schedule, meta={'group_id': group_id})

    def parse_schedule(self, response):
        group_id = response.meta['group_id']
        current_date = None
        try:
            for row in response.css('tr.shadow'):
                cells = row.css('td')
                if len(cells) == 1:
                    current_date = cells[0].css('::text').get().strip()
                elif len(cells) == 5:
                    loader = LessonLoader(item=LessonItem(), selector=row)
                    loader.add_value('group_id', group_id)
                    loader.add_value('date', current_date)
                    loader.add_value('lesson_number', cells[0])
                    loader.add_value('subject_title', cells[1])
                    loader.add_value('classroom_title', cells[2])
                    loader.add_value('teacher_fullname', cells[3])
                    loader.add_value('subgroup', cells[4])

                    lesson = loader.load_item()
                    self.lessons.append(lesson)

                else:
                    raise ValueError(f"Некорректная структура таблицы. В строке {len(cells)} ячеек")

        except Exception as e:
            self.logger.error(f"Ошибка обработки страницы: {e}")
            self.scraped_group_ids.discard(group_id)

    def closed(self, reason):
        # Этот метод вызывается при завершении работы паука
        if self.scraped_group_ids:
            # Преобразуем список уроков в JSON
            lessons_json = json.dumps(self.lessons)
            group_ids_json = json.dumps(self.scraped_group_ids)

            # Помещаем данные в Redis
            self.redis_client.set("lesson_scraped_data", lessons_json)
            self.redis_client.set("scraped_group_ids", group_ids_json)

        self.logger.info("Паук завершен. Данные сохранены в Redis.")
