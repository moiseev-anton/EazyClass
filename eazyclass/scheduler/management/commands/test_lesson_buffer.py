from django.core.management.base import BaseCommand
from ...tasks import synchronize_lessons


class Command(BaseCommand):
    help = 'Тестирует работу сохранения/изменения/деактивации уроков в БД.'

    def handle(self, *args, **kwargs):
        # Создаем начальный стандартный шаблон звонков в БД
        group_ids = {295, 349, 317}
        # Вызываем задачу заполнения расписания напрямую
        synchronize_lessons(group_ids)