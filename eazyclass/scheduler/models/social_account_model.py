from django.db import models

from scheduler.managers.social_account_manager import SocialAccountManager


class SocialAccount(models.Model):
    PLATFORM_CHOICES = [
        ('telegram', 'Telegram'),
        ('vk', 'VKontakte'),
    ]

    user = models.ForeignKey('scheduler.User', related_name='profiles', on_delete=models.CASCADE)
    provider = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    social_id = models.CharField(max_length=50)
    extra_data = models.JSONField(blank=True, null=True)

    objects = SocialAccountManager()

    class Meta:
        unique_together = ('provider', 'social_id')

    def __str__(self):
        return f"{self.user} - {self.provider} ({self.social_id})"
