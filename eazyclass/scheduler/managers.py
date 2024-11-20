from django.db import models
from typing import Dict, Optional, Tuple, Any
from django.core.exceptions import ObjectDoesNotExist
from django.contrib.auth.models import BaseUserManager

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


class UserManager(BaseUserManager):
    @cache_data('user_data_{0}', timeout=USER_DATA_CACHE_TIMEOUT, cache_name='telegrambot_cache')
    def get_user_data_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        user = self.filter(telegram_id=telegram_id).first()
        if user is None:
            logger.warning(f'Пользователь с telegram_id {telegram_id} не найден.')
            return None
        logger.info(f'Получены данные пользователя с telegram_id {telegram_id} из БД.')
        return user.to_dict()

    @invalidate_cache('user_data_{0}', cache_name='telegrambot_cache')
    def update_contact(self, telegram_id: str, contact) -> 'User':
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

    def get_or_create_by_telegram_user(self, telegram_user) -> Tuple['User', bool]:
        try:
            user, created = self.get_or_create(
                telegram_id=telegram_user.id,
                defaults={
                    'first_name': telegram_user.first_name or '',
                    'last_name': telegram_user.last_name or '',
                    'is_active': True
                }
            )
            if created:
                logger.info(f"Создан новый пользователь Telegram: {user.username} (ID: {user.id})")
            else:
                logger.info(f"Пользователь Telegram найден: {user.username} (ID: {user.id})")
            return user, created
        except Exception as e:
            logger.error(f"Ошибка при создании пользователя через Telegram: {e}")
            raise

    @invalidate_cache('user_data_{0}', cache_name='telegrambot_cache')
    def update_contact(self, telegram_id: int, contact) -> Optional['User']:
        user = self.filter(telegram_id=telegram_id).first()
        if user:
            user.phone = contact.phone_number
            user.first_name = contact.first_name or user.first_name
            user.last_name = contact.last_name or user.last_name
            user.save(update_fields=['phone', 'first_name', 'last_name'])
            logger.info(f"Контактные данные обновлены для пользователя Telegram ID {telegram_id}.")
            return user
        logger.warning(f'Не найден пользователь для обновления контактов по telegram_id {telegram_id}.')
        return None

    @invalidate_cache('user_data_{0}', cache_name='telegrambot_cache')
    def reset_subgroup(self, user_id: int) -> int:
        updated_count = self.filter(id=user_id).update(subgroup='0')
        logger.debug(f"Сброшена подгруппа для пользователя с ID {user_id}")
        return updated_count

    def create_user(self, username: str, password: Optional[str] = None, **extra_fields) -> 'User':
        if not username:
            raise ValueError('Имя пользователя (username) обязательно для создания учетной записи')

        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        user.save(using=self._db)
        logger.info(f"Создан новый пользователь: {user.username} (ID: {user.id})")
        return user

    def create_superuser(self, username: str, password: str, **extra_fields) -> 'User':
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Суперпользователь должен иметь is_staff=True')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Суперпользователь должен иметь is_superuser=True')

        return self.create_user(username, password, **extra_fields)
