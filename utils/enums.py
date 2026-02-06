from enum import StrEnum


class KeyEnum(StrEnum):
    SCRAPED_LESSONS = "scrapy:scraped_lesson_items"
    SCRAPED_GROUPS = "scrapy:scraped_group_ids"
    PAGE_HASH_PREFIX = 'scrapy:content_hash:group_id:'
    SCRAPY_SUMMARY = "scrapy:summary"
    MAIN_PAGE_HASH = "scrapy:last_version_main_page_hash"
    SYNCED_GROUPS_PREFIX = "scrapy:synced_groups:"
    UNCHANGED_GROUPS = "scrapy:unchanged_groups"