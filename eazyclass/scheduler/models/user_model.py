from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from scheduler.managers import UserManager
from scheduler.models.abstract_models import TimestampedModel


class User(TimestampedModel, AbstractBaseUser, PermissionsMixin):
    username = models.CharField(max_length=30, unique=True, )
    first_name = models.CharField(max_length=150, blank=True, null=True)
    last_name = models.CharField(max_length=150, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_superuser = models.BooleanField(default=False)
    # + updated_at из TimestampedModel
    # + created_at из TimestampedModel

    objects = UserManager()

    USERNAME_FIELD = "username"

    class Meta:
        indexes = [models.Index(fields=['username'])]

    def __str__(self):
        return f"{self.first_name or ''} {self.last_name or ''} ({self.username or ''}) [ID: {self.id}]"
