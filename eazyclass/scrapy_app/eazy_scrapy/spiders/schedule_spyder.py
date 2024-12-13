import scrapy
import re
from urllib.parse import urljoin

from scheduler.models import Group  # Импорт модели Group
from scrapy_app.eazy_scrapy.items import ScheduleItem


class ScheduleSpider(scrapy.Spider):
    name = 'schedule_spider'
    base_url = 'https://bincol.ru/rasp/'
    DATE_PATTERN = re.compile(r'\d{2}\.\d{2}\.\d{4}')

    def start_requests(self):
        # Получаем список групп и ссылок из БД
        group_links = Group.objects.link_map()  # Получаем список кортежей (group_id, link)

        # Проходим по всем ссылкам и отправляем запросы
        for group_id, link in group_links:
            url = urljoin(self.base_url, link)
            yield scrapy.Request(url=url, callback=self.parse_schedule, meta={'group_id': group_id})

    def parse_schedule(self, response):
        group_id = response.meta['group_id']

        current_date = None  # переменная для хранения текущей даты

        # Ищем все строки таблицы с классом 'shadow' (уроки и даты)
        for row in response.css('tr.shadow'):
            # Извлекаем количество ячеек в строке
            cells = row.css('td')
            # Если в строке 1 ячейка, то это строка с датой
            if len(cells) == 1:
                current_date = cells[0].get().strip()  # извлекаем дату
            # Если в строке 5 ячеек, то это строка с уроком
            elif len(cells) == 5:
                # Создаем Item для урока
                item = ScheduleItem(
                    group_id=group_id,
                    lesson_number=cells[0].css('td::text').get().strip(),
                    subject_title=cells[1].css('td::text').get().strip() or 'Не указано',
                    classroom_title=cells[2].css('td::text').get().strip() or '(дист)',
                    teacher_fullname=cells[3].css('td::text').get().strip() or 'Не указано',
                    subgroup=cells[4].css('td::text').get().strip() or 0,
                    date=current_date
                )

                yield item
