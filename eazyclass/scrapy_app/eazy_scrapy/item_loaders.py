from itemloaders.processors import MapCompose, TakeFirst
from scrapy.loader import ItemLoader

from scheduler.models import Subject, Classroom, Teacher

SUBJECT_DEFAULT_VALUE = 'Не указано'
TEACHER_DEFAULT_VALUE = 'Не указано'
CLASSROOM_DEFAULT_VALUE = '(дист)'
SUBGROUP_DEFAULT_VALUE = 0
MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field('title').max_length
MAX_CLASSROOM_TITLE_LENGTH = Classroom._meta.get_field('title').max_length
MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field('full_name').max_length


class LessonLoader(ItemLoader):
    # Обработчики на входе (input)
    subject_title_in = MapCompose(str.strip, str.title)
    classroom_title_in = MapCompose(str.strip)
    teacher_fullname_in = MapCompose(str.strip)
    subgroup_in = MapCompose(int)  # Преобразуем в число
    lesson_number_in = MapCompose(int)

    # Обработчик для даты
    date_in = MapCompose(str.strip)
    date_out = TakeFirst()  # Возвращаем только первое значение

    # Обработчики на выходе (output)
    lesson_number_out = TakeFirst()  # Возвращаем только первое значение