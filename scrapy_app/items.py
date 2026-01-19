import scrapy


class LessonItem(scrapy.Item):
    group_id = scrapy.Field()
    lesson_number = scrapy.Field()
    subject_title = scrapy.Field()
    classroom_title = scrapy.Field()
    teacher_fullname = scrapy.Field()
    subgroup = scrapy.Field()
    date = scrapy.Field()
