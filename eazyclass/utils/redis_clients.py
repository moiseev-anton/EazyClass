import redis
from django.conf import settings


def get_scrapy_redis_client():
    return redis.from_url(settings.REDIS_SCRAPY_URL)
