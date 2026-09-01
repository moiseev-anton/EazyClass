from enum import auto, Flag, StrEnum

class KeyEnum(StrEnum):
    SCRAPED_LESSONS = "scrapy:scraped_lesson_items"
    SCRAPED_GROUPS = "scrapy:scraped_group_ids"
    PAGE_HASH_PREFIX = 'scrapy:content_hash:group_id:'
    SCRAPY_SUMMARY = "scrapy:summary"
    MAIN_PAGE_HASH = "scrapy:last_version_main_page_hash"
    SYNCED_GROUPS_PREFIX = "scrapy:synced_groups:"
    UNCHANGED_GROUPS = "scrapy:unchanged_groups"

class Defaults:
    TEACHER_NAME = "не указано"
    SUBJECT_TITLE = "не указано"
    SUBGROUP = "0"
    PERIOD_PART = 0
    CLASSROOM = "дист"


class LessonDisplayMode(Flag):
    SHOW_GROUP = auto()
    SHOW_TEACHER = auto()
    SHOW_SUBGROUP = auto()

    # Предустановленные режимы
    FOR_GROUP = SHOW_TEACHER | SHOW_SUBGROUP
    FOR_TEACHER = SHOW_GROUP | SHOW_SUBGROUP
    FULL = SHOW_GROUP | SHOW_TEACHER | SHOW_SUBGROUP
