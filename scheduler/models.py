from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from polymorphic.models import PolymorphicModel

from .managers import GroupManager, TeacherManager, SubscriptionManager, UserManager


class BaseSubscription(PolymorphicModel):
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='subscriptions')

    objects = SubscriptionManager()

    class Meta:
        abstract = True

    def get_subscription_details(self):
        raise NotImplementedError("Этот метод должен быть реализован в наследуемых классах")


class Faculty(models.Model):
    title = models.CharField(max_length=255)
    short_title = models.CharField(max_length=10, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['short_title']),  # для сортировки
        ]

    def calculate_short_title(self):
        if not self.groups.exists():
            self.short_title = ''
        else:
            titles = [group.title.lstrip('0123456789-_ ') for group in self.groups.all()]
            result = titles[0]

            for title in titles[1:]:
                result = ''.join(t1 if t1 == t2 else '' for t1, t2 in zip(result, title)).rstrip('0123456789-_ ')

            self.short_title = result
            self.save(update_fields=['short_title'])

    def __str__(self):
        return f"{self.short_title}"


class Group(models.Model):
    title = models.CharField(max_length=255)
    link = models.URLField()
    faculty = models.ForeignKey(Faculty, related_name='groups', on_delete=models.CASCADE, null=True)
    grade = models.CharField(max_length=1)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    objects = GroupManager()

    class Meta:
        indexes = [
            models.Index(fields=['is_active']),
            models.Index(fields=['grade', 'title']),  # для сортировки
        ]

    def __str__(self):
        return f"{self.title}"


class Teacher(models.Model):
    full_name = models.CharField(max_length=64, unique=True)
    short_name = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)

    object = TeacherManager()

    def __str__(self):
        return f"{self.short_name}"

    def save(self, *args, **kwargs):
        if not self.short_name:
            self.short_name = self.generate_short_name()
        super().save(*args, **kwargs)

    def generate_short_name(self):
        full_name = str(self.full_name).strip()
        if full_name in ("не указано", ""):
            self.full_name = "не указано"
            return "не указано"

        names = full_name.split()
        short_name = names[0]  # Берем первый элемент полностью

        # Добавляем первые буквы второго и третьего элементов, если они есть
        if len(names) > 1:
            short_name += f" {names[1][0]}."
        if len(names) > 2:
            short_name += f"{names[2][0]}."

        return short_name


class Subject(models.Model):
    title = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title}"


class Classroom(models.Model):
    title = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.title}"


class LessonTime(models.Model):
    date = models.DateField()
    lesson_number = models.CharField(max_length=1)
    start_time = models.TimeField(null=True)
    end_time = models.TimeField(null=True)

    class Meta:
        unique_together = ('date', 'lesson_number')
        indexes = [
            models.Index(fields=['date', 'lesson_number']),
            models.Index(fields=['date']),
        ]

    def save(self, *args, **kwargs):
        if not self.start_time or not self.end_time:
            try:
                template = LessonTimeTemplate.objects.get(day_of_week=self.date.strftime('%A'),
                                                          lesson_number=self.lesson_number)
                self.start_time = template.start_time
                self.end_time = template.end_time
            except ObjectDoesNotExist:
                self.start_time = None
                self.end_time = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.lesson_number} пара"


class Lesson(models.Model):
    group = models.ForeignKey(Group, related_name='lessons', on_delete=models.CASCADE, null=True)
    lesson_time = models.ForeignKey(LessonTime, related_name='lessons', on_delete=models.CASCADE, null=True)
    subject = models.ForeignKey(Subject, related_name='lessons', on_delete=models.CASCADE, null=True)
    teacher = models.ForeignKey(Teacher, related_name='lessons', on_delete=models.CASCADE, null=True)
    classroom = models.ForeignKey(Classroom, related_name='lessons', on_delete=models.CASCADE, null=True)
    subgroup = models.CharField(max_length=1, default='0')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.group.title}({self.subgroup})-{self.lesson_time}-{self.subject}"

    class Meta:
        indexes = [
            models.Index(fields=['group', 'lesson_time']),
            models.Index(fields=['group', 'lesson_time', 'subgroup']),
        ]


class LessonBuffer(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True)
    lesson_time = models.ForeignKey(LessonTime, on_delete=models.CASCADE, null=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, null=True)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, null=True)
    subgroup = models.CharField(max_length=1, default='0')
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['group', 'lesson_time']),
            models.Index(fields=['group', 'lesson_time', 'subgroup']),
        ]

    def __str__(self):
        return f"{self.group.title}({self.subgroup})-{self.lesson_time}-{self.subject}"


class User(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    user_name = models.CharField(max_length=32)
    first_name = models.CharField(max_length=32)
    last_name = models.CharField(max_length=32)
    phone_number = models.CharField(max_length=15)
    subgroup = models.CharField(max_length=1, default='0')
    is_active = models.BooleanField(default=True)
    registration_date = models.DateTimeField(auto_now_add=True)
    # Настройка уведомлений
    notify_on_schedule_change = models.BooleanField(default=True)
    notify_on_lesson_start = models.BooleanField(default=True)

    objects = UserManager

    class Meta:
        indexes = [
            models.Index(fields=['telegram_id', 'is_active']),
        ]

    def __str__(self):
        return f"{self.user_name} ({self.first_name} {self.last_name}) [ID: {self.id}]"

    def get_subscriptions(self) -> list[dict]:
        subscriptions = []
        for subscription in self.subscriptions.all():
            subscription_data = subscription.get_subscription_details()
            subscriptions.append(subscription_data)
        return subscriptions

    def to_dict(self):
        return {
            'user_id': self.id,
            'telegram_id': self.telegram_id,
            'user_name': self.user_name,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'phone_number': self.phone_number,
            'subgroup': self.subgroup,
            'notify_on_schedule_change': self.notify_on_schedule_change,
            'notify_on_lesson_start': self.notify_on_lesson_start,
            'subscriptions': self.get_subscriptions()
        }


class GroupSubscription(BaseSubscription):
    group = models.ForeignKey('Group', on_delete=models.CASCADE, related_name='subscriptions')

    class Meta:
        unique_together = ('user', 'group')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['group']),
        ]

    def get_subscription_details(self):
        return {
            'model': 'Group',
            'id': self.group.id,
            'title': self.group.title
        }


class TeacherSubscription(BaseSubscription):
    teacher = models.ForeignKey('Teacher', on_delete=models.CASCADE, related_name='subscriptions')

    class Meta:
        unique_together = ('user', 'teacher')
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['teacher']),
        ]

    def get_subscription_details(self):
        return {
            'model': 'Teacher',
            'id': self.teacher.id,
            'title': self.teacher.short_name
        }


class LessonTimeTemplate(models.Model):
    day_of_week = models.CharField(max_length=10, choices=[
        ('Monday', 'Понедельник'),
        ('Tuesday', 'Вторник'),
        ('Wednesday', 'Среда'),
        ('Thursday', 'Четверг'),
        ('Friday', 'Пятница'),
        ('Saturday', 'Суббота')
    ])
    lesson_number = models.IntegerField()
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        unique_together = ('day_of_week', 'lesson_number')

    def __str__(self):
        return f"{self.get_day_of_week_display()} - Пара {self.lesson_number}: {self.start_time} - {self.end_time}"
