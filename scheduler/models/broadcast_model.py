from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from scheduler.broadcasts.rules import (
    ChannelMode, default_audience, validate_audience, validate_platforms,
)
from scheduler.models.abstract_models import TimestampedModel


class Broadcast(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        QUEUED = "queued", "Ожидает обработки"
        SENDING = "sending", "Отправляется"
        COMPLETED = "completed", "Завершена"
        INTERRUPTED = "interrupted", "Прервана"

    title = models.CharField("Название", max_length=255)
    text = models.TextField("Текст сообщения")
    audience = models.JSONField("Аудитория", default=default_audience, validators=[validate_audience])
    channel_mode = models.CharField(
        "Режим каналов", max_length=20, choices=ChannelMode.choices, default=ChannelMode.ALL_AVAILABLE,
    )
    selected_platforms = models.JSONField(
        "Выбранные каналы", default=list, blank=True, validators=[validate_platforms],
    )
    resolved_platforms = models.JSONField(default=list, blank=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, editable=False, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="created_broadcasts", editable=False,
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="started_broadcasts", editable=False,
    )
    queued_at = models.DateTimeField(null=True, blank=True, editable=False)
    started_at = models.DateTimeField(null=True, blank=True, editable=False)
    finished_at = models.DateTimeField(null=True, blank=True, editable=False)
    progress_updated_at = models.DateTimeField(null=True, blank=True, editable=False)
    statistics = models.JSONField(default=dict, blank=True, editable=False)
    error = models.TextField(blank=True, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Рассылка"
        verbose_name_plural = "Рассылки"
        permissions = [("send_broadcast", "Can send broadcasts")]

    def clean(self):
        super().clean()
        validate_audience(self.audience)
        validate_platforms(self.selected_platforms)
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValidationError({"text": "Текст сообщения не должен быть пустым."})
        if self.channel_mode == ChannelMode.SELECTED and not self.selected_platforms:
            raise ValidationError({"selected_platforms": "Выберите хотя бы один канал."})
        if self.channel_mode == ChannelMode.ALL_AVAILABLE and self.selected_platforms:
            raise ValidationError({"selected_platforms": "В режиме всех каналов список должен быть пустым."})
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).first()
            immutable = ("title", "text", "audience", "channel_mode", "selected_platforms")
            if previous and previous.status != self.Status.DRAFT:
                if any(getattr(self, field) != getattr(previous, field) for field in immutable):
                    raise ValidationError("Запущенную рассылку нельзя редактировать.")

    def __str__(self):
        return self.title
