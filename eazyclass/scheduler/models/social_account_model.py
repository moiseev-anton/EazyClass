from django.db import models

from scheduler.managers.social_account_manager import SocialAccountManager


class Platform(models.TextChoices):
    TELEGRAM = 'telegram', 'Telegram'
    VK = 'vk', 'VKontakte'


class SocialAccount(models.Model):
    user = models.ForeignKey('scheduler.User', related_name='accounts', on_delete=models.CASCADE)
    platform = models.CharField(max_length=10, choices=Platform.choices)
    social_id = models.CharField(max_length=50)
    extra_data = models.JSONField(blank=True, null=True)

    objects = SocialAccountManager()

    class Meta:
        unique_together = ('platform', 'social_id')

    def __str__(self):
        return f"{self.user} - {self.platform} ({self.social_id})"
