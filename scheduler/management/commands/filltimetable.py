from django.core.management.base import BaseCommand
from ...models import LessonTimeTemplate
from datetime import time


def fill_lesson_times(days, times):
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


class Command(BaseCommand):
    help = 'Заполняет шаблон расписания звонков стандартными значениями'

    def handle(self, *args, **kwargs):
        weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
        saturday = 'Saturday'

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

        fill_lesson_times(weekdays, weekday_times)
        fill_lesson_times([saturday], saturday_times)

        self.stdout.write(self.style.SUCCESS('Default lesson times filled successfully'))
