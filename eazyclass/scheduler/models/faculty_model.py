from django.db import models

from scheduler.models.abstract_models import TimestampedModel


class Faculty(TimestampedModel):
    title = models.CharField(max_length=255)
    short_title = models.CharField(max_length=10, blank=True)
    is_active = models.BooleanField(default=True)
    # + created_at из TimestampedModel
    # + updated_at из TimestampedModel

    class Meta:
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["short_title"]),  # для сортировки
        ]

        verbose_name = 'Faculty'
        verbose_name_plural = 'Faculties'

    def calculate_short_title(self):
        if not self.groups.exists():
            self.short_title = ""
        else:
            titles = [
                group.title.lstrip("0123456789-_ ") for group in self.groups.all()
            ]
            result = titles[0]

            for title in titles[1:]:
                result = "".join(
                    t1 if t1 == t2 else "" for t1, t2 in zip(result, title)
                ).rstrip("0123456789-_ ")

            self.short_title = result
            self.save(update_fields=["short_title"])

    def __str__(self):
        return f"{self.short_title}"
