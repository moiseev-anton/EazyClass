import datetime
import uuid
from datetime import timedelta, date as DateClass
from django.db import models

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils.timezone import now

from scheduler.managers import (
    GroupManager,
    TeacherManager,
    SubjectManager,
    ClassroomManager,
    PeriodTemplateManager,
    PeriodManager,
    UserManager,
    SubscriptionManager,
)


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

    def get_display_name(self):
        return self.title


class Teacher(models.Model):
    full_name = models.CharField(max_length=64, unique=True)
    short_name = models.CharField(max_length=30)
    is_active = models.BooleanField(default=True)

    objects = TeacherManager()

    class Meta:
        indexes = [
            models.Index(fields=['full_name']),
        ]

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

    def get_display_name(self):
        return self.short_name


class Subject(models.Model):
    title = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    objects = SubjectManager()

    class Meta:
        indexes = [
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return f"{self.title}"


class Classroom(models.Model):
    title = models.CharField(max_length=10, unique=True)
    is_active = models.BooleanField(default=True)

    objects = ClassroomManager()

    class Meta:
        indexes = [
            models.Index(fields=['title']),
        ]

    def __str__(self):
        return f"{self.title}"


class PeriodTemplate(models.Model):
    lesson_number = models.PositiveIntegerField()
    start_date = models.DateField(default=DateClass.today)
    end_date = models.DateField(null=True, blank=True, default=None)

    objects = PeriodTemplateManager()

    class Meta:
        db_table = "scheduler_period_template"
        ordering = ['start_date']
        unique_together = ('lesson_number', 'start_date')

    def __str__(self):
        return f"Урок {self.lesson_number} с {self.start_date} по {self.end_date}"


class Timing(models.Model):
    period_template = models.ForeignKey(PeriodTemplate, related_name='timings', on_delete=models.CASCADE)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                check=models.Q(end_time__gt=models.F('start_time')),
                name='check_timing_start_before_end',
            ),
        ]

    # @property
    # def active_days(self) -> set[str]:
    #     """
    #     Возвращает множество активных дней недели для текущего шаблона.
    #     """
    #     # Получаем все связанные записи через ForeignKey
    #     days = self.weekdays.all().values_list('day_of_week', flat=True)
    #     day_names = {
    #         0: 'Пн', 1: 'Вт', 2: 'Ср', 3: 'Чт', 4: 'Пт', 5: 'Сб', 6: 'Вс'
    #     }
    #     return {day_names[day] for day in days}
    #


class TimingWeekDay(models.Model):
    """
    Модель для связывания шаблона расписания с днями недели.
    """
    timing = models.ForeignKey(Timing, related_name='weekdays', on_delete=models.CASCADE)
    day_of_week = models.SmallIntegerField()  # 0 для понедельника, 1 для вторника и т.д.

    class Meta:
        unique_together = ('timing', 'day_of_week')


class Period(models.Model):
    lesson_number = models.PositiveIntegerField()
    date = models.DateField()
    start_time = models.TimeField(default=None, null=True, blank=True)
    end_time = models.TimeField(default=None, null=True, blank=True)

    objects = PeriodManager()

    class Meta:
        unique_together = ('date', 'lesson_number')
        indexes = [
            models.Index(fields=['date', 'lesson_number']),
            models.Index(fields=['date']),
        ]

    def save(self, *args, **kwargs) -> None:
        self.pre_save_actions()
        super().save(*args, **kwargs)

    def pre_save_actions(self):
        """
        Дополняет объект Period значениями start_time и end_time из шаблона.
        Если шаблон отсутствует, start_time и end_time остаются None.
        """
        if not self.start_time or not self.end_time:
            template = PeriodTemplate.objects.get_template_for_day(date=self.date, lesson_number=self.lesson_number)
            if template and template.timing.exists():
                timing = template.timings.first()
                self.start_time = timing.start_time
                self.end_time = timing.end_time

    def __str__(self) -> str:
        return f"{self.date} - {self.lesson_number} пара: {self.start_time} - {self.end_time}"


class Lesson(models.Model):
    group = models.ForeignKey(Group, related_name='lessons', on_delete=models.CASCADE, null=True)
    period = models.ForeignKey(Period, related_name='lessons', on_delete=models.CASCADE, null=True)
    subject = models.ForeignKey(Subject, related_name='lessons', on_delete=models.CASCADE, null=True)
    teacher = models.ForeignKey(Teacher, related_name='lessons', on_delete=models.CASCADE, null=True)
    classroom = models.ForeignKey(Classroom, related_name='lessons', on_delete=models.CASCADE, null=True)
    subgroup = models.CharField(max_length=1, default='0')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.group.title}({self.subgroup})-{self.period}-{self.subject}"

    class Meta:
        indexes = [
            models.Index(fields=['group', 'period']),
            models.Index(fields=['group', 'period', 'subgroup']),
        ]


class LessonBuffer(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE, null=True)
    period = models.ForeignKey(Period, on_delete=models.CASCADE, null=True)
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, null=True)
    teacher = models.ForeignKey(Teacher, on_delete=models.CASCADE, null=True)
    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, null=True)
    subgroup = models.CharField(max_length=1, default='0')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "scheduler_lesson_buffer"
        indexes = [
            models.Index(fields=['group', 'period']),
            models.Index(fields=['group', 'period', 'subgroup']),
        ]

    def __str__(self):
        return f"{self.group.title}({self.subgroup})-{self.period}-{self.subject}"


class User(AbstractUser):
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    phone = models.CharField(max_length=15, unique=True, null=True, blank=True)
    subgroup = models.CharField(max_length=1, default='0')
    email = models.EmailField(unique=True, blank=True, null=True)

    # Настройка уведомлений
    notify_on_schedule_change = models.BooleanField(default=True)
    notify_on_lesson_start = models.BooleanField(default=True)

    objects = UserManager()

    REQUIRED_FIELDS = []

    class Meta:
        indexes = [
            models.Index(fields=['telegram_id', 'is_active']),
        ]

    def __str__(self):
        return f"{self.username} ({self.first_name} {self.last_name}) [ID: {self.id}]"

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
            'user_name': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'phone_number': self.phone,
            'subgroup': self.subgroup,
            'notify_on_schedule_change': self.notify_on_schedule_change,
            'notify_on_lesson_start': self.notify_on_lesson_start,
            'subscriptions': self.get_subscriptions()
        }


class AuthToken(models.Model):
    user = models.ForeignKey("User", on_delete=models.CASCADE, related_name="auth_tokens")
    token = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    def is_valid(self):
        return now() < self.expires_at

    @staticmethod
    def generate_token(user):
        token = f"auth_{uuid.uuid4().hex}"
        return AuthToken.objects.create(
            user=user,
            token=token,
            expires_at=now() + timedelta(minutes=10),  # Токен действует 10 минут
        )


class Subscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscriptions')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        unique_together = ('user', 'content_type', 'object_id')
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
        ]

    def __str__(self):
        return f'{self.user} is subscribed to {self.content_object}'

    def get_subscription_details(self):
        details = {
            'id': self.object_id,
            'model': self.content_type.name,
            'name': self.content_object.get_display_name() if hasattr(self.content_object,
                                                                      'get_display_name') else 'N/A'
        }
        return details


class LessonNotificationQueue(models.Model):
    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="notifications")
    data_key = models.CharField(max_length=255)  # Ключ в Redis
    is_sent = models.BooleanField(default=False)  # флаг для отслеживания отправки уведомления
    created_at = models.DateTimeField(auto_now_add=True)  # дата и время создания уведомления
    # updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "scheduler_lesson_notification_queue"
        unique_together = ('group', 'teacher', 'period')  # исключаем дублирующие записи

    def __str__(self):
        return f"Уведомление для группы {self.group.id}, преподавателя {self.teacher.id}, времени урока {self.period.id}"
