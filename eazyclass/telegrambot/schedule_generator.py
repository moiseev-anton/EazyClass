import datetime
from scheduler.models import Lesson


def get_schedule_for_today(group_id):
    date_today = datetime.date.today()
    # Предположим, у нас есть функция get_schedule_data, которая принимает ID группы и дату
    return fetch_schedule_data(group_id, date_today)


def get_schedule_for_tomorrow(group_id):
    date_tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    return fetch_schedule_data(group_id, date_tomorrow)


def get_schedule_for_week(group_id):
    date_today = datetime.date.today()
    start_week = date_today - datetime.timedelta(days=date_today.weekday())  # Понедельник текущей недели
    end_week = start_week + datetime.timedelta(days=6)  # Воскресенье текущей недели
    return fetch_schedule_data(group_id, start_week, end_week)


def get_schedule_for_end_of_week(group_id):
    date_today = datetime.date.today()
    end_week = date_today + datetime.timedelta(days=(6 - date_today.weekday()))  # Воскресенье текущей недели
    return fetch_schedule_data(group_id, date_today, end_week)


def fetch_schedule_data(group_id, start_date, end_date=None):
    # Если конечная дата не указана, используем начальную дату как конечную
    if end_date is None:
        end_date = start_date

    # Формируем запрос к БД для получения занятий
    lessons = Lesson.objects.select_related(
        'period', 'subject', 'teacher', 'classroom'
    ).filter(
        group_id=group_id,
        period__date__range=(start_date, end_date),
        is_active=True
    ).order_by('period__date', 'period__lesson_number')

    return lessons
