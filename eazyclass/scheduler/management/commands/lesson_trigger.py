from django.core.management.base import BaseCommand, CommandError

from scheduler.activities.triggers import execute_trigger_action


class Command(BaseCommand):
    help = "Управляет триггером в БД для уведомлений об изменениях расписания"

    def add_arguments(self, parser):
        parser.add_argument(
            'action',
            type=str,
            choices=['create', 'drop'],
            help="Действие: 'create' для создания триггера, 'drop' для удаления триггера."
        )

    def handle(self, *args, **options):
        action = options['action']
        try:
            message = execute_trigger_action(action)
            self.stdout.write(self.style.SUCCESS(message))
        except Exception as e:
            raise CommandError(f"Ошибка при выполнении действия '{action}': {e}")
