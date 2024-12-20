from django.core.management.base import BaseCommand
from scheduler.tasks import fill_periods
from scheduler.activities.period_activities import fill_default_period_template


class Command(BaseCommand):
    help = 'Заполняет таблицу с расписанием и выполняет другие начальные настройки для проекта.'

    def handle(self, *args, **kwargs):
        # Создаем начальный стандартный шаблон звонков в БД
        try:
            self.stdout.write('Заполнение шаблона времени уроков...')
            fill_default_period_template()
            self.stdout.write(self.style.SUCCESS('Шаблон времени уроков успешно заполнен.'))

            self.stdout.write("Применения шаблона к расписанию...")
            fill_periods()
            self.stdout.write(self.style.SUCCESS("Шаблон применен успешно применен"))

            self.stdout.write(self.style.SUCCESS("Все начальные настройки выполнены успешно!"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Произошла ошибка при заполнении шаблона: {e}'))



