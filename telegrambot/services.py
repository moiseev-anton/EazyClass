import logging

from django.apps import apps
from django.db import transaction
from django.core.cache import caches
from django.db.models import Model
from scheduler.models import User, BaseSubscription
from scheduler.managers import SubscriptionManager
from telebot.types import User as TelegramUser

CACHE_TIMEOUT = 86400  # 24 часа
USER_DATA_CACHE_TIMEOUT = 3600  # 1 час

cache = caches['telegram-bot']
logger = logging.getLogger(__name__)


class CacheService:

    @staticmethod
    def get_cached_keyboard_data(model: Model, cache_key: str):
        if not hasattr(model, 'objects'):
            raise ValueError(f"Model does not have a manager")

        if not hasattr(model.objects, 'active_keyboard_data'):
            raise ValueError("Manager does not implement active_keyboard_data method")

        data = cache.get(cache_key)
        if not data:
            data = list(model.objects.active_keyboard_data())
            cache.set(cache_key, data, timeout=CACHE_TIMEOUT)
        return data

    @staticmethod
    def get_cached_user_data(telegram_id: int) -> dict:
        cache_key = f"user_data_{telegram_id}"
        user_data = cache.get(cache_key)

        if not user_data:
            CacheService.cache_user_data(telegram_id=telegram_id)

        return user_data

    @staticmethod
    def update_user_context(telegram_id: int, context: dict):
        cache_key = f"user_data_{telegram_id}"
        user_data = CacheService.get_cached_user_data(telegram_id)
        user_data['context'] = context
        cache.set(cache_key, user_data, timeout=USER_DATA_CACHE_TIMEOUT)
        return user_data

    @staticmethod
    def cache_user_data(user=None, telegram_id=None, timeout=USER_DATA_CACHE_TIMEOUT) -> dict:
        if telegram_id is not None:
            try:
                user = User.objects.get(telegram_id=telegram_id)
            except User.DoesNotExist:
                logger.warning(f'Не удалось получить пользователь с telegram_id {telegram_id} из БД')
                raise

        if user is not None:
            try:
                cache_key = f"user_data_{user.telegram_id}"
                user_data = user.to_dict()
                cache.set(cache_key, user_data, timeout=timeout)
                logger.debug(f'Пользовательские данные кэшированы для telegram_id {user.telegram_id}')
                return user_data
            except Exception as e:
                logger.warning(f'Ошибка кеширования данных пользователя: {str(e)}')
                raise
        else:
            raise ValueError('Необходимо указать объект пользователя или telegram_id')

    @staticmethod
    def invalidate_user_cache(telegram_id: int):
        cache_key = f"user_data_{telegram_id}"
        cache.delete(cache_key)


class UserService:
    @staticmethod
    def sign_up_user(telegram_user: TelegramUser) -> bool:
        user, created = User.objects.get_or_create_by_telegram_user(telegram_user)
        CacheService.cache_user_data(user=user)
        return created


class SubscriptionService:
    @staticmethod
    def create_subscription(user_id: int, model_name: str, obj_id: int):

        with transaction.atomic():
            # Инвалидация всех существующих подписок пользователя
            BaseSubscription.objects.invalidate_all_subscriptions(user_id)

            # Сброс подгруппы пользователя
            User.objects.reset_subgroup(user_id)

            # Создание новой подписки
            subscription_model = apps.get_model('scheduler', f'{model_name.capitalize()}Subscription')
            subscription = subscription_model.objects.create(user_id=user_id, **{model_name.lower(): obj_id})
            return subscription
