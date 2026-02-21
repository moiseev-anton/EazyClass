import re

from django.db import models

from scheduler.managers import TeacherManager
from enums import Defaults


INITIALS_PATTERN = re.compile(
    r"^[А-ЯЁA-Z][а-яёa-z-]+\s+[А-ЯЁA-Z]\.(?:[А-ЯЁA-Z]\.)?$"
)


class Teacher(models.Model):
    full_name = models.CharField(max_length=64, unique=True)
    short_name = models.CharField(max_length=30)
    endpoint = models.CharField(max_length=128, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    objects = TeacherManager()

    class Meta:
        ordering = ["full_name"]
        indexes = [
            models.Index(fields=["full_name"]),
        ]
        verbose_name = 'Teacher'
        verbose_name_plural = 'Teachers'

    def __str__(self):
        return f"{self.short_name}"

    def save(self, *args, **kwargs):
        if not self.short_name:
            self.short_name = self.generate_short_name()
        super().save(*args, **kwargs)

    def pre_save_actions(self):
        if not self.short_name:
            self.short_name = self.generate_short_name()

    def generate_short_name(self):
        full_name = str(self.full_name).strip()
        default_name = Defaults.TEACHER_NAME
        if full_name in (default_name, ""):
            self.full_name = default_name
            return default_name

        if INITIALS_PATTERN.match(full_name):
            return full_name

        names = full_name.split()
        short_name = names[0]  # Берем первый элемент полностью

        # Добавляем первые буквы второго и третьего элементов, если они есть
        if len(names) > 1:
            short_name += f" {names[1][0]}."
        if len(names) > 2:
            short_name += f"{names[2][0]}."

        return short_name
