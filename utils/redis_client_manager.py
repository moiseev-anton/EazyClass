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
            logger.error(msg)
            raise ValueError(msg)

        if alias not in RedisClientManager._clients:
            try:
                logger.info(f'Создаем и кешируем (сингтоним) redis клиента {alias}')
                redis_url = settings.REDIS_CONFIG[alias]
                RedisClientManager._clients[alias] = redis.from_url(
                    redis_url, decode_responses=True,
                )

            except redis.ConnectionError as e:
                logger.error(f"Ошибка подключения к Redis для alias '{alias}': {e}")
                raise
            except Exception as e:
                logger.error(f"Неизвестная ошибка при создании Redis клиента для alias '{alias}': {e}")
                raise

        logger.info(f'Получаем готовый redis клиент {alias}')
        return RedisClientManager._clients[alias]
