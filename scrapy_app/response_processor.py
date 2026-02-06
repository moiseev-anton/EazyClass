import hashlib
import logging
from typing import List, Dict, Optional

from scrapy_app.item_loaders import LessonLoader
from scrapy_app.items import LessonItem
from utils import RedisClientManager, KeyEnum

logger = logging.getLogger(__name__)


class ResponseProcessor:
    """
    Класс для обработки и парсинга ответа (scrapy.http.Response), вычисления хеша контента и проверки его изменений.

    :param response: Ответ, содержащий страницу для парсинга.
    :param redis_client: (необязательно) Клиент Redis.
    """
    DATE_ROW_LENGTH = 1
    HTML_SNIPPET_LIMIT = 200
    FIELD_ORDER = ('lesson_number', 'subject_title', 'classroom_title', 'teacher_fullname', 'subgroup',)

    def __init__(self, response: 'scrapy.http.Response', redis_client: Optional['redis.client.Redis'] = None):
        self.response = response
        self.group_id = response.meta.get('group_id')
        if self.group_id is None:
            raise ValueError("Отсутствует group_id в response.meta")

        self.redis_client = redis_client or RedisClientManager.get_client('scrapy')
        self.content_hash = self._calculate_content_hash()
        self.content_changed = self._check_content_changed()
        self.current_date = None
        self.lessons = []

    def extract_lessons(self) -> List[Dict]:
        """
        Основной метод парсинга страницы.

        Проходит по всем строкам таблицы и извлекает данные о дате или занятиях.
        Если структура строки некорректна, выбрасывается ошибка.
        """
        try:
            logger.debug('Начинается парсинг страницы')
            self.validate_page()

            for row in self.response.xpath('//tr[@class="shadow"]'):
                row_cells_texts = row.xpath('./td').xpath('string(.)').getall()

                if len(row_cells_texts) == self.DATE_ROW_LENGTH:
                    # Строка содержит дату
                    self.current_date = row_cells_texts[0]

                elif len(row_cells_texts) == len(self.FIELD_ORDER) and self.current_date is not None:
                    # Строка содержит данные о занятии
                    loader = LessonLoader(item=LessonItem())

                    for field, text in zip(self.FIELD_ORDER, row_cells_texts):
                        loader.add_value(field, text)

                    loader.add_value('group_id', int(self.group_id))
                    loader.add_value('date', self.current_date)

                    lesson = loader.load_item_dict()
                    self.lessons.append(lesson)
                else:
                    raise ValueError(f"Некорректная структура таблицы")
            logger.info(f'Получено {len(self.lessons)} уроков для group_id: {self.group_id}.')
            return self.lessons
        except Exception as e:
            raise RuntimeError(f"Ошибка парсинга страницы (group_id: {self.group_id}): {e}")

    def get_content_hash(self) -> str:
        """Возвращает пару (group_id, content_hash)."""
        return self.content_hash

    def is_content_changed(self) -> bool:
        """Возвращает флаг, показывающий, изменился ли контент страницы."""
        return self.content_changed

    def _calculate_content_hash(self) -> str:
        """Метод для вычисления MD5 хэша содержимого response.body."""
        content = self.response.body
        if not content:
            raise ValueError(f"Пустое тело ответа для group_id {self.group_id}.")

        if isinstance(content, bytes):
            return hashlib.md5(content).hexdigest()

        if isinstance(content, str):
            return hashlib.md5(content.encode('utf-8')).hexdigest()

        raise TypeError(f"Неверный тип response.body: {type(content)}. Ожидался bytes или str")

    def _check_content_changed(self) -> bool:
        """
        Проверяет, был ли изменен контент на странице, сравнив текущий хеш с хранимым в Redis.
        Возвращает True, если контент изменился, иначе False.
        """
        redis_key = f'{KeyEnum.PAGE_HASH_PREFIX}{self.group_id}'
        try:
            if previous_hash := self.redis_client.get(redis_key):
                return self.content_hash != previous_hash
            return True

        except (ConnectionError, TimeoutError) as e:
            logger.error(f"Ошибка соединения с Redis при получении предыдущего хеша страницы {self.group_id}: {e}")
        except Exception as e:
            logger.error(f"Неизвестная ошибка при проверке изменения контента для group_id  {self.group_id}: {e}")
        return False

    def validate_page(self):
        if self.response.xpath('//table//tr[@class="shadow"]').get() is None:
            html_preview = self.response.text[:self.HTML_SNIPPET_LIMIT]
            raise RuntimeError(f"Страница не соответствует ожидаемой структуре (group_id={self.group_id}). "
                               f"Начало содержимого:\n{html_preview}...")
