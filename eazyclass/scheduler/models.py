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
    start_time = models.TimeField()
    end_time = models.TimeField()
    start_date = models.DateField(default=DateClass.today)
    end_date = models.DateField(null=True, blank=True, default=None)

    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)

    objects = PeriodTemplateManager()

    class Meta:
        db_table = "scheduler_period_template"

    def clean(self) -> None:
        """
        Метод для валидации пересечений дней недели для шаблонов с одинаковым номером урока.
        Проверяется, что дни недели не пересекаются для шаблонов с одинаковым номером урока в указанный период времени.
        """
        if self.end_date and self.end_date <= self.start_date:
            raise ValidationError('End date должна быть позже start date.')

        active_days = self.active_days

        # Проверка конфликтов с другими шаблонами с одинаковым номером урока
        overlapping_templates = PeriodTemplate.objects.filter(
            lesson_number=self.lesson_number,
            start_date__lte=self.end_date if self.end_date else self.start_date,
            end_date__gte=self.start_date
        ).exclude(pk=self.pk)

        for template in overlapping_templates:
            overlapping_days = active_days & template.active_days
            if overlapping_days:
                raise ValidationError(
                    f"Уже есть действующий шаблон для {self.lesson_number} пересекающийся по дням недели: "
                    f"{', '.join(overlapping_days)}.")

    @property
    def active_days(self) -> set[str]:
        """
        Возвращает множество активных дней недели для текущего шаблона.
        """
        days = {
            'Пн': self.monday,
            'Вт': self.tuesday,
            'Ср': self.wednesday,
            'Чт': self.thursday,
            'Пт': self.friday,
            'Сб': self.saturday,
            'Вс': self.sunday,
        }
        return {day for day, is_active in days.items() if is_active}

    def save(self, *args, **kwargs) -> None:
        self.clean()  # Валидация перед сохранением
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        active_days = self.active_days
        return f"Пара {self.lesson_number}: {self.start_time} - {self.end_time} ({', '.join(active_days)})"





class Period(models.Model):
    lesson_number = models.PositiveIntegerField()
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)

    objects = PeriodManager()

    class Meta:
        unique_together = ('date', 'lesson_number')
        indexes = [
            models.Index(fields=['date', 'lesson_number']),
            models.Index(fields=['date']),
        ]

    def save(self, *args, **kwargs) -> None:
        if not self.start_time or not self.end_time:
            template = PeriodTemplate.objects.get_template_for_day(date=self.date, lesson_number=self.lesson_number)
            self.start_time, self.end_time = (None, None) if not template else (template.start_time, template.end_time)
        super().save(*args, **kwargs)

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
    group = models.ForeignKey('Group', on_delete=models.CASCADE)  # или используйте свойство group_id
    teacher = models.ForeignKey('Teacher', on_delete=models.CASCADE)
    period = models.ForeignKey('Period', on_delete=models.CASCADE)
    notification_date = models.DateField()  # дата, когда урок был изменен
    is_notified = models.BooleanField(default=False)  # флаг для отслеживания отправки уведомления

    class Meta:
        db_table = "scheduler_lesson_notification_queue"
        unique_together = ('group', 'teacher', 'period')  # исключаем дублирующие записи
        indexes = [
            models.Index(fields=['is_notified']),
        ]

    def __str__(self):
        return f"Уведомление для группы {self.group.id}, преподавателя {self.teacher.id}, времени урока {self.period.id}"
