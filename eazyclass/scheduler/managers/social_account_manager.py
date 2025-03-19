import logging

from django.db import models, transaction

logger = logging.getLogger(__name__)


class SocialAccountManager(models.Manager):

    def is_exists(self, provider, social_id):
        return self.filter(provider=provider, social_id=social_id).exists()

    @transaction.atomic
    def create_account(self, provider, social_id, user, extra_data=None):
        if self.is_exists(provider=provider, social_id=social_id):
            raise ValueError(f"Аккаунт '{provider}' c id:'{social_id}' уже существует.")

        return self.create(
            provider=provider,
            social_id=social_id,
            user=user,
            extra_data=extra_data or {}
        )

