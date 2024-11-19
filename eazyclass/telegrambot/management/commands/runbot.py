from django.core.management.base import BaseCommand
from ...tasks import start_telegram_bot


class Command(BaseCommand):
    help = 'Заполняет таблицу с расписанием и выполняет другие начальные настройки для проекта.'

    def handle(self, *args, **kwargs):
        start_telegram_bot()

