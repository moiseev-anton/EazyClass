from enum import StrEnum


class KeyEnum(StrEnum):
    MAIN_PAGE_HASH = "scrapy:main_page_hash"
    SCRAPED_LESSONS = "scrapy:scraped_lesson_items"
    SCRAPED_GROUPS = "scrapy:scraped_group_ids"
    PAGE_HASH_PREFIX = 'scrapy:content_hash:group_id:'
    SCRAPY_SUMMARY = "scrapy:summary"