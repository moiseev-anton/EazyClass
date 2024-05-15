from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, timedelta
from ...models import LessonTime, LessonTimeTemplate
from django.db import transaction
from django.db.models import Max


class Command(BaseCommand):
    help = 'Применяет изменения в шаблоне ко всем существующим данным, начиная с заданной даты.'

    def add_arguments(self, parser):
        parser.add_argument('start_date', type=str, help='Дата ДД-ММ-ГГГГ, с которой будут применены изменения.')

    def handle(self, *args, **kwargs):
        start_date_str = kwargs['start_date']
        try:
            start_date = datetime.strptime(start_date_str, '%d-%m-%Y').date()
        except ValueError:
            self.stdout.write(self.style.ERROR('Неверный формат даты. Используйте формат ДД-ММ-ГГГГ.'))
            return

        today = timezone.now().date()
        if start_date >= today:
            self.apply_changes(start_date)
            self.stdout.write(self.style.SUCCESS(f'Звонки успешно изменены с {start_date}.'))
        else:
            self.stdout.write(self.style.ERROR('Дата начала не может быть в прошлом.'))

    def apply_changes(self, start_date):
        """
        Применяет изменения в шаблоне ко всем существующим данным, начиная с заданной даты.
        """
        end_date = LessonTime.objects.aggregate(max_date=Max('date'))['max_date']

        if end_date:
            with transaction.atomic():
                for single_date in (start_date + timedelta(n) for n in range((end_date - start_date).days + 1)):
                    day_of_week = single_date.strftime('%A')
                    templates = LessonTimeTemplate.objects.filter(day_of_week=day_of_week)
                    for template in templates:
                        LessonTime.objects.filter(date=single_date, lesson_number=template.lesson_number).update(
                            start_time=template.start_time,
                            end_time=template.end_time
                        )
        else:
            self.stdout.write(self.style.WARNING('Нет записей в таблице LessonTime для обновления.'))
