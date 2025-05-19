from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    updated_at = models.DateTimeField(default=timezone.now)

    def save(self, *args, **kwargs):
        """Обновляет updated_at при каждом сохранении."""
        self.updated_at = timezone.now()
        super().save(*args, **kwargs)

    class Meta:
        abstract = True
