import pytest
from unittest.mock import patch
from django.conf import settings
from utils.redis_client_manager import RedisClientManager


# Тест на успешное создание клиента Redis через RedisClientManager
def test_get_client_success():
    # Проверяем, что в settings.REDIS_CONFIG есть нужный alias
    redis_url = settings.REDIS_CONFIG.get('default')
    if not redis_url:
        pytest.skip("No 'default' Redis configuration found in settings.REDIS_CONFIG.")

    with patch('redis.from_url') as mock_redis:
        mock_redis.return_value = 'RedisClient'  # Мокируем возврат клиента

        # Сброс кеша RedisClientManager перед запуском теста
        RedisClientManager._clients.clear()

        # Получаем клиента через RedisClientManager
        client = RedisClientManager.get_client('default')

        # Проверяем, что redis.from_url был вызван с правильным URL из настроек
        mock_redis.assert_called_once_with(redis_url)

        # Проверяем, что возвращенный клиент — это тот, который мы настроили
        assert client == 'RedisClient'


# Тест на отсутствие alias в конфигурации
def test_get_client_alias_not_found():
    with pytest.raises(ValueError,
                       match="Redis configuration for alias 'nonexistent' not found in settings.REDIS_CONFIG."):
        RedisClientManager.get_client('nonexistent')


# Тест на кеширование клиентов
def test_client_caching():
    redis_url = settings.REDIS_CONFIG.get('default')
    if not redis_url:
        pytest.skip("No 'default' Redis configuration found in settings.REDIS_CONFIG.")

    with patch('redis.from_url') as mock_redis:
        mock_redis.return_value = 'RedisClient'

        # Сброс кеша RedisClientManager перед запуском теста
        RedisClientManager._clients.clear()

        # Первый вызов
        client1 = RedisClientManager.get_client('default')
        # Второй вызов (должен вернуть тот же клиент из кеша)
        client2 = RedisClientManager.get_client('default')

        # Проверяем, что метод from_url был вызван только один раз
        mock_redis.assert_called_once_with(redis_url)

        # Проверяем, что оба клиента одинаковы
        assert client1 == client2


# Тест на создание разных клиентов для разных alias
def test_get_client_different_aliases():
    redis_url_default = settings.REDIS_CONFIG.get('default')
    redis_url_scrapy = settings.REDIS_CONFIG.get('scrapy')

    if not redis_url_default or not redis_url_scrapy:
        pytest.skip("No 'default' or 'other' Redis configuration found in settings.REDIS_CONFIG.")

    with patch('redis.from_url') as mock_redis:
        # Мокируем возврат клиентов для двух разных alias
        mock_redis.side_effect = ['RedisClientDefault', 'RedisClientScrapy']

        # Сброс кеша RedisClientManager перед запуском теста
        RedisClientManager._clients.clear()

        # Получаем клиенты для двух разных alias
        client_default = RedisClientManager.get_client('default')
        client_scrapy = RedisClientManager.get_client('scrapy')

        # Проверяем, что для разных alias были получены разные клиенты
        assert client_default == 'RedisClientDefault'
        assert client_scrapy == 'RedisClientScrapy'

        # Проверяем, что redis.from_url был вызван дважды с правильными URL
        mock_redis.assert_any_call(redis_url_default)
        mock_redis.assert_any_call(redis_url_scrapy)

        # Убедимся, что два клиента не одинаковы
        assert client_default != client_scrapy
