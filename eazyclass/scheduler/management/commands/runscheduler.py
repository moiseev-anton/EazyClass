from django.core.management.base import BaseCommand
from scheduler.tasks import fill_lesson_times
from scheduler.activities import fill_default_lesson_time_template


class Command(BaseCommand):
    help = 'Заполняет таблицу с расписанием и выполняет другие начальные настройки для проекта.'

    def handle(self, *args, **kwargs):
        # Создаем начальный стандартный шаблон звонков в БД
        fill_default_lesson_time_template()
        # Вызываем задачу заполнения расписания напрямую
        fill_lesson_times()

