import logging

from scrapy_app.item_loaders import LessonLoader
from scrapy_app.items import LessonItem

logger = logging.getLogger(__name__)


class SchedulePageParser:
    """Парсер страницы расписания.

    Используется для извлечения данных о занятиях и датах из HTML-ответа.
    Формирует список словарей с данными для каждого отдельного занятия.

    """
    DATE_ROW_LENGTH = 1
    FIELD_ORDER = ('lesson_number', 'subject_title', 'classroom_title', 'teacher_fullname', 'subgroup',)

    def __init__(self, response):
        """Инициализирует парсер страницы расписания.

        Args:
            response: Объект ответа Scrapy, содержащий HTML-страницу для парсинга.
        """
        self.response = response
        self.group_id = response.meta['group_id']
        self.current_date = None
        self.lessons = []

    def parse(self):
        """Основной метод парсинга страницы.

        Проходит по всем строкам таблицы и извлекает данные о дате или занятиях.
        Если структура строки некорректна, выбрасывается ошибка.

        Returns:
            list: Список словарей с данными о занятиях.

        Raises:
            RuntimeError: Если возникла ошибка в процессе парсинга страницы.
        """
        try:
            logger.info('Начинается парсинг страницы')
            for row in self.response.xpath('//tr[@class="shadow"]'):
                row_cells_texts = row.xpath('./td').xpath('string(.)').getall()

                if len(row_cells_texts) == self.DATE_ROW_LENGTH:
                    # Строка содержит дату
                    self.current_date = row_cells_texts[0]

                elif len(row_cells_texts) == len(self.FIELD_ORDER):
                    # Строка содержит данные о занятии
                    loader = LessonLoader(item=LessonItem())

                    for field, text in zip(self.FIELD_ORDER, row_cells_texts):
                        loader.add_value(field, text)

                    loader.add_value('group_id', self.group_id)
                    loader.add_value('date', self.current_date)

                    lesson = loader.load_item_dict()
                    logger.info(lesson)
                    self.lessons.append(lesson)
                else:
                    raise ValueError(f"Некорректная структура таблицы")

            return self.lessons
        except Exception as e:
            raise RuntimeError(f"Ошибка парсинга страницы: {e}")
