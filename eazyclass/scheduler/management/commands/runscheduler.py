from django.core.management.base import BaseCommand

from scheduler.activities import fill_default_period_template, execute_trigger_action


class Command(BaseCommand):
    help = 'Заполняет таблицу с расписанием и выполняет другие начальные настройки для проекта.'

    def handle(self, *args, **kwargs):
        # Создаем начальный стандартный шаблон звонков в БД
        try:
            self.stdout.write('Заполнение шаблона времени уроков...')
            fill_default_period_template()
            self.stdout.write(self.style.SUCCESS('Шаблон времени уроков успешно заполнен.'))

            self.stdout.write('Создание триггера в БД...')
            execute_trigger_action(action='create')
            self.stdout.write(self.style.SUCCESS('Триггер в БД успешно заполнен.'))
            # Место для других начальных настоек

            self.stdout.write(self.style.SUCCESS("Все стартовые настройки выполнены успешно!"))
        except Exception as e:
            self.stderr.write(self.style.ERROR(f'Произошла ошибка при стартовой настройке: {e}'))



