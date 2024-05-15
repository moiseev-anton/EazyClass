from datetime import time
from django.db import transaction
from .models import LessonTimeTemplate


def make_active(modeladmin, request, queryset):
    queryset.update(is_active=True)


make_active.short_description = "Сделать активными выбранные записи"


def make_inactive(modeladmin, request, queryset):
    queryset.update(is_active=False)


make_inactive.short_description = "Сделать НЕ активными выбранные записи"


def toggle_active(modeladmin, request, queryset):
    for obj in queryset:
        obj.is_active = not obj.is_active
        obj.save()


toggle_active.short_description = "Переключить активность выбранных записей"


def reset_timetable(modeladmin, request, queryset):
    @transaction.atomic
    def reset_data():
        # Удаляем все существующие записи
        LessonTimeTemplate.objects.all().delete()

        # Временные интервалы для понедельника-пятницы
        weekday_times = [
            {'lesson_number': 1, 'start_time': time(8, 0), 'end_time': time(9, 35)},
            {'lesson_number': 2, 'start_time': time(9, 45), 'end_time': time(11, 20)},
            {'lesson_number': 3, 'start_time': time(12, 20), 'end_time': time(13, 55)},
            {'lesson_number': 4, 'start_time': time(14, 5), 'end_time': time(15, 40)},
            {'lesson_number': 5, 'start_time': time(15, 50), 'end_time': time(17, 25)},
            {'lesson_number': 6, 'start_time': time(17, 35), 'end_time': time(19, 10)},
        ]

        # Временные интервалы для субботы
        saturday_times = [
            {'lesson_number': 1, 'start_time': time(8, 0), 'end_time': time(9, 35)},
            {'lesson_number': 2, 'start_time': time(9, 45), 'end_time': time(11, 20)},
            {'lesson_number': 3, 'start_time': time(11, 50), 'end_time': time(13, 25)},
            {'lesson_number': 4, 'start_time': time(13, 35), 'end_time': time(15, 10)},
            {'lesson_number': 5, 'start_time': time(15, 20), 'end_time': time(16, 55)},
            {'lesson_number': 6, 'start_time': time(17, 5), 'end_time': time(18, 40)},
        ]

        weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        saturday = ['Saturday']

        fill_timetable(weekdays, weekday_times)
        fill_timetable(saturday, saturday_times)

    reset_data()
    modeladmin.message_user(request, "Lesson times have been reset to default values successfully.")


reset_timetable.short_description = "Сбросить таблицу звонков"


def fill_timetable(days, times):
    for day in days:
        for lesson in times:
            LessonTimeTemplate.objects.get_or_create(
                day_of_week=day,
                lesson_number=lesson['lesson_number'],
                defaults={
                    'start_time': lesson['start_time'],
                    'end_time': lesson['end_time']
                }
            )
