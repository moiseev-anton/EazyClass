from scrapy_app.eazy_scrapy.item_loaders import LessonLoader
from scrapy_app.eazy_scrapy.items import LessonItem


class SchedulePageParser:
    DATE_ROW_LENGTH = 1
    LESSON_ROW_LENGTH = 5

    def __init__(self, response):
        self.response = response
        self.current_date = None
        self.lessons = []

    def parse(self):
        try:
            group_id = self.response.meta['group_id']
            for row in self.response.css('tr.shadow'):
                cells = row.css('td')
                if len(cells) == self.DATE_ROW_LENGTH:
                    self.current_date = cells[0].css('::text').get().strip()
                elif len(cells) == self.LESSON_ROW_LENGTH:
                    loader = self.parse_lesson_row(cells)
                    loader.add_value('group_id', group_id)
                    loader.add_value('date', self.current_date)
                    lesson = loader.load_item()
                    self.lessons.append(lesson)
                else:
                    raise ValueError(f"Некорректная структура таблицы")

            return self.lessons
        except Exception as e:
            raise RuntimeError(f"Ошибка парсинга страницы: {e}")

    @staticmethod
    def parse_lesson_row(cells):
        loader = LessonLoader(item=LessonItem())
        loader.add_value('lesson_number', cells[0])
        loader.add_value('subject_title', cells[1])
        loader.add_value('classroom_title', cells[2])
        loader.add_value('teacher_fullname', cells[3])
        loader.add_value('subgroup', cells[4])
        return loader
