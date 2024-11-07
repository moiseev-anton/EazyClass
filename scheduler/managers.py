from django.db import models
from typing import Any, Dict
from django.core.exceptions import ObjectDoesNotExist
from .models import User

from .utils import cache_data, invalidate_cache
import logging

CACHE_TIMEOUT = 86400  # 24 часа
USER_DATA_CACHE_TIMEOUT = 3600  # 1 час
KEYBOARD_DATA_CACHE_TIMEOUT = 82800  # 23 часа

logger = logging.getLogger(__name__)


class BaseManager(models.Manager):
    def active_keyboard_data(self):
        raise NotImplementedError("Subclasses must implement fetch_active_data method")


class GroupManager(BaseManager):
    def active_keyboard_data(self):
        return (self.filter(is_active=True).values('id', 'title', 'grade', 'faculty__short_title')
                .order_by('faculty__short_title', 'grade', 'title'))


class TeacherManager(BaseManager):
    def active_keyboard_data(self):
        return self.filter(is_active=True).values('id', 'short_name').order_by('short_name')


class SubscriptionManager(models.Manager):
    def invalidate_all_subscriptions(self, user_id: int):
        self.filter(user_id=user_id).delete()


class UserManager(models.Manager):
    def get_or_create_by_telegram_user(self, telegram_user) -> (User, bool):
        user, created = self.get_or_create(
            telegram_id=str(telegram_user.id),
            defaults={
                'first_name': telegram_user.first_name,
                'last_name': telegram_user.last_name or '',
                'is_active': True
            }
        )
        return user, created

    @cache_data('user_data_{0}', timeout=USER_DATA_CACHE_TIMEOUT, cache_name='telegrambot_cache')
    def get_user_data_by_telegram_id(self, telegram_id: int) -> Dict[str, Any]:
        try:
            user = self.get(telegram_id=telegram_id)
            user_data = user.to_dict()
            return user_data
        except ObjectDoesNotExist as e:
            logger.warning(f'Не удалось получить пользователя с telegram_id {telegram_id} из БД: {str(e)}')
            raise

    @invalidate_cache('user_data_{0}', cache_name='telegrambot_cache')
    def update_contact(self, telegram_id: str, contact) -> User:
        user, created = self.update_or_create(
            telegram_id=telegram_id,
            defaults={
                'phone_number': contact.phone_number,
                'first_name': contact.first_name,
                'last_name': contact.last_name,
            }
        )

        return user

    def reset_subgroup(self, user_id: int):
        self.filter(id=user_id).update(subgroup='0')
