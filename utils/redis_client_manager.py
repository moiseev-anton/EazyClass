import logging

import redis
from django.conf import settings

logger = logging.getLogger(__name__)


class RedisClientManager:
    """Управляет созданием и кешированием Redis-клиентов."""
    _clients = {}

    @staticmethod
    def get_client(alias='default') -> redis.Redis:
        """
        Возвращает Redis-клиент для указанного alias.
        """
        if alias not in settings.REDIS_CONFIG:
            msg = f"Настройки подключения для '{alias}' не найдены в settings.REDIS_CONFIG."
            raise ValueError(msg)

        if alias not in RedisClientManager._clients:
            logger.debug("Создаётся Redis-клиент", extra={"event": "redis.client.created"})
            redis_url = settings.REDIS_CONFIG[alias]
            RedisClientManager._clients[alias] = redis.from_url(redis_url, decode_responses=True)

        return RedisClientManager._clients[alias]
