import logging

from django.core.management.base import BaseCommand, CommandError
from eazyclass.logging_config import safe_error_context

from scheduler.activities import fill_default_period_template


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Заполняет таблицу с расписанием и выполняет другие начальные настройки для проекта.'

    def handle(self, *args, **kwargs):
        logger.info("Начинается заполнение стандартного шаблона звонков",
                    extra={"event": "maintenance.template.started"})
        # Создаем начальный стандартный шаблон звонков в БД
        try:
            self.stdout.write('Заполнение шаблона времени уроков...')
            fill_default_period_template()
            logger.info("Стандартный шаблон звонков заполнен",
                        extra={"event": "maintenance.template.completed"})
            self.stdout.write(self.style.SUCCESS('Шаблон времени уроков успешно заполнен.'))

            self.stdout.write(self.style.SUCCESS("Все стартовые настройки выполнены успешно!"))
        except Exception as exc:
            logger.error("Не удалось заполнить стандартный шаблон звонков",
                         extra={"event": "maintenance.template.failed", **safe_error_context(exc)})
            raise CommandError("Не удалось заполнить шаблон звонков; подробности в логах.") from None
