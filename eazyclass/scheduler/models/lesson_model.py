from django.db import models


class Lesson(models.Model):
    group = models.ForeignKey('scheduler.Group', related_name='lessons', on_delete=models.CASCADE, null=True)
    period = models.ForeignKey('scheduler.Period', related_name='lessons', on_delete=models.CASCADE, null=True)
    subject = models.ForeignKey('scheduler.Subject', related_name='lessons', on_delete=models.CASCADE, null=True)
    teacher = models.ForeignKey('scheduler.Teacher', related_name='lessons', on_delete=models.CASCADE, null=True)
    classroom = models.ForeignKey('scheduler.Classroom', related_name='lessons', on_delete=models.CASCADE, null=True)
    subgroup = models.CharField(max_length=1, default='0')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.group.title}({self.subgroup})-{self.period}-{self.subject}"

    class Meta:
        indexes = [
            models.Index(fields=['period', 'group']),
            models.Index(fields=['group', 'period', 'subgroup']),
        ]
