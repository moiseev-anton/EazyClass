import logging
from typing import Any, Dict, List

from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.contenttypes.models import ContentType
from django.core.cache import caches
from django.db import transaction
from telebot.types import User as TelegramUser

from scheduler.models import User, Subscription
from scheduler.utils import cache_data

CACHE_TIMEOUT = 86400  # 24 часа
USER_DATA_CACHE_TIMEOUT = 3600  # 1 час
KEYBOARD_DATA_CACHE_TIMEOUT = 82800  # 23 часа


cache = caches['telegrambot_cache']
logger = logging.getLogger(__name__)


class CacheService:
    @staticmethod
    def update_user_context(telegram_id: int, context: Dict[str, Any]) -> Dict[str, Any]:
        cache_key = f"user_data_{telegram_id}"
        user_data = CacheService.get_user_data_by_telegram_id(telegram_id)
        user_data['context'] = context
        cache.set(cache_key, user_data, timeout=USER_DATA_CACHE_TIMEOUT)
        return user_data

    @staticmethod
    def cache_user_data(user: User, timeout: int = USER_DATA_CACHE_TIMEOUT) -> Dict[str, Any]:
        user_data = user.to_dict()
        cache_key = f"user_data_{user.telegram_id}"
        cache.set(cache_key, user_data, timeout=timeout)
        logger.debug(f'Пользовательские данные кэшированы для telegram_id {user.telegram_id}')
        return user_data

    @staticmethod
    def invalidate_user_cache(telegram_id: int) -> None:
        cache_key = f"user_data_{telegram_id}"
        cache.delete(cache_key)


class ContentTypeService:
    @staticmethod
    @cache_data('content_type_{0}_{1}', timeout=CACHE_TIMEOUT)
    def get_content_type_id(app_label: str, model_name: str) -> int:
        try:
            content_type = ContentType.objects.get(app_label=app_label, model_name=model_name)
            return content_type.id
        except ObjectDoesNotExist:
            logger.error(f"ContentType not found for {app_label}.{model_name}")
            raise


class UserService:
    @staticmethod
    def sign_up_user(telegram_user: TelegramUser) -> bool:
        user, created = User.objects.get_or_create_by_telegram_user(telegram_user)
        CacheService.cache_user_data(user=user)
        return created


class KeyboardDataService:
    # ВАЖНО чтобы время кеширования было меньше чем период обновления клавиатур.
    # Иначе будут использованы старые данные из кеша
    @staticmethod
    @cache_data('keyboard_data_{0}', timeout=KEYBOARD_DATA_CACHE_TIMEOUT, cache_name='telegrambot_cache')
    def get_data_for_dynamic_keyboard(model_name: str) -> List[Dict[str, Any]]:
        model = apps.get_model('scheduler', model_name)

        if not hasattr(model, 'objects'):
            raise ValueError(f"Model does not have a manager")

        if not hasattr(model.objects, 'active_keyboard_data'):
            raise ValueError("Manager does not implement active_keyboard_data method")

        data = list(model.objects.active_keyboard_data())
        return data


class SubscriptionService:
    @staticmethod
    def create_subscription(user_id: int, model_name: str, obj_id: int) -> Subscription:
        with transaction.atomic():
            content_type_id = ContentTypeService.get_content_type_id(app_label='scheduler',
                                                                     model_name=model_name.lower())
            # Инвалидация всех существующих подписок пользователя
            Subscription.objects.invalidate_all_subscriptions(user_id)

            # Сброс подгруппы пользователя
            User.objects.reset_subgroup(user_id)

            # Создание новой подписки
            subscription = Subscription.objects.create(
                user_id=user_id,
                content_type_id=content_type_id,
                object_id=obj_id
            )
            return subscription
