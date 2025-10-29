import logging
import random

from django.contrib.auth.models import BaseUserManager
from django.db import transaction

logger = logging.getLogger(__name__)


class UserManager(BaseUserManager):
    def _generate_default_username(self):
        """Генерация случайного уникального имени пользователя."""
        while True:
            username = f"s{random.randint(100000, 999999)}"
            if not self.model.objects.filter(username=username).exists():
                return username

    @transaction.atomic
    def _create_user(self, social_id, platform, chat_id=None, first_name=None, last_name=None, extra_data=None, **extra_fields):
        from scheduler.models import SocialAccount, Platform

        if platform not in [p.value for p in Platform]:
            raise ValueError(f"Недопустимая платформа: {platform}. Допустимые значения: {[p.value for p in Platform]}")

        if SocialAccount.objects.filter(platform=platform, social_id=social_id).exists():
            raise ValueError(f"Аккаунт {platform} c id:{social_id} уже существует.")

        user = self.model(
            first_name=first_name,
            last_name=last_name,
            username=self._generate_default_username(),
            **extra_fields
        )
        user.set_unusable_password()
        user.save(using=self._db)

        # Привязываем к платформе (Telegram/VK)
        SocialAccount.objects.create(
            user=user,
            platform=platform,
            chat_id=chat_id,
            social_id=social_id,
            extra_data=extra_data
        )
        return user

    def create_user(self, social_id, platform, chat_id=None, first_name=None, last_name=None, extra_data=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        return self._create_user(social_id, platform, chat_id, first_name, last_name, extra_data, **extra_fields)

    def create_superuser(self, social_id, platform, chat_id=None, first_name=None, last_name=None, extra_data=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        if chat_id is None:
            chat_id = social_id

        return self._create_user(social_id, platform, chat_id,  first_name, last_name, extra_data, **extra_fields)

    @transaction.atomic
    def get_or_create_user(self, social_id, platform, chat_id=None, first_name=None, last_name=None, extra_data=None, **extra_fields):
        from scheduler.models import SocialAccount

        try:
            social_account = SocialAccount.objects.get(platform=platform, social_id=social_id)
            return social_account.user, False
        except SocialAccount.DoesNotExist:
            user = self.create_user(
                social_id=social_id,
                platform=platform,
                chat_id=chat_id,
                first_name=first_name,
                last_name=last_name,
                extra_data=extra_data,
                **extra_fields
            )
            return user, True
