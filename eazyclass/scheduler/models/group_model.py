from django.db import models

from scheduler.managers import GroupManager


class Group(models.Model):
    title = models.CharField(max_length=255)
    link = models.URLField()
    faculty = models.ForeignKey('scheduler.Faculty', related_name='groups', on_delete=models.CASCADE, null=True)
    grade = models.CharField(max_length=1)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    objects = GroupManager()

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return f"{self.title}"

    def get_display_name(self):
        return self.title