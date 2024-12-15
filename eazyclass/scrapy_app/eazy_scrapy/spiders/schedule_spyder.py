import scrapy
from urllib.parse import urljoin

from scheduler.models import Group  # Импорт модели Group
from scrapy_app.eazy_scrapy.item_loaders import LessonLoader
from scrapy_app.eazy_scrapy.items import LessonItem


class ScheduleSpider(scrapy.Spider):
    name = 'schedule_spider'
    base_url = 'https://bincol.ru/rasp/'

    def start_requests(self):
        # Получаем список групп и ссылок из БД
        group_links = Group.objects.link_map()  # Получаем список кортежей (group_id, link)

        # Проходим по всем ссылкам и отправляем запросы
        for group_id, link in group_links:
            url = urljoin(self.base_url, link)
            yield scrapy.Request(url=url, callback=self.parse_schedule, meta={'group_id': group_id})

    def parse_schedule(self, response):
        try:
            group_id = response.meta['group_id']
            current_date = None
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

                    yield loader.load_item()

                else:
                    raise ValueError(f"Некорректная структура таблицы. В строке {len(cells)} ячеек")

        except Exception as e:
            self.logger.error(f"Ошибка обработки страницы: {e}")

