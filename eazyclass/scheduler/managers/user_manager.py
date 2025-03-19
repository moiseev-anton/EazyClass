import logging
import random



from django.contrib.auth.models import BaseUserManager
from django.db import transaction

logger = logging.getLogger(__name__)


class UserManager(BaseUserManager):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._user_fields = None

    @property
    def user_fields(self):
        if self._user_fields is None:
            self._user_fields = {field.name for field in self.model._meta.get_fields()}
        return self._user_fields

    def _generate_default_username(self):
        while True:
            username = f"s{random.randint(100000, 999999)}"
            if not self.model.objects.filter(username=username).exists():
                return username

    def _filter_user_fields(self, extra_fields):
        user_data = {key: value for key, value in extra_fields.items() if key in self.user_fields}
        extra_data = {key: value for key, value in extra_fields.items() if key not in self.user_fields}
        return user_data, extra_data

    @transaction.atomic
    def _create_user(self, social_id, provider, first_name=None, last_name=None, **extra_fields):
        from scheduler.models import SocialAccount
        if not social_id:
            raise ValueError('Уникальный идентификатор должен быть указан')
        if not provider:
            raise ValueError('Провайдер аутентификации должен быть указан')
        if SocialAccount.objects.is_exists(provider=provider, social_id=social_id):
            raise ValueError(f"Аккаунт '{provider}' c id:'{social_id}' уже существует.")

        user_data, extra_data = self._filter_user_fields(extra_fields)

        logger.info(f'Пробуем создать User')

        user = self.model(
            first_name=first_name,
            last_name=last_name,
            username=self._generate_default_username(),
            **user_data
        )
        user.set_unusable_password()
        user.save(using=self._db)
        logger.info(f'Создали User')

        # Привязываем к платформе (Telegram/VK)
        logger.info(f'Начинаем создание SocialAccount')
        SocialAccount.objects.create_account(
            user=user,
            provider=provider,
            social_id=social_id,
            extra_data=extra_data
         )
        return user

    def create_user(self, social_id, provider, first_name=None, last_name=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        return self._create_user(social_id, provider, first_name, last_name, **extra_fields)

    def create_superuser(self, social_id, provider, first_name=None, last_name=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        logger.info(f'Начинаем создание суперпользователя {(social_id, provider, first_name, last_name)}')

        return self._create_user(social_id, provider, first_name, last_name, **extra_fields)