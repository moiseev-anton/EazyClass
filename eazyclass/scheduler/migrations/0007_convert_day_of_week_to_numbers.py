from django.db import migrations


def convert_day_of_week(apps, schema_editor):
    PeriodTemplate = apps.get_model('scheduler', 'PeriodTemplate')

    # Сопоставляем строковые значения с числовыми
    days_of_week_map = {
        'Monday': 0,  # Понедельник
        'Tuesday': 1,  # Вторник
        'Wednesday': 2,  # Среда
        'Thursday': 3,  # Четверг
        'Friday': 4,  # Пятница
        'Saturday': 5,  # Суббота
        'Sunday': 6, # Воскресение
    }

    for template in PeriodTemplate.objects.all():
        # Обновляем строковое значение на числовое
        template.day_of_week = days_of_week_map.get(template.day_of_week, template.day_of_week)
        template.save()


class Migration(migrations.Migration):
    dependencies = [
        ('scheduler', '0006_periodtemplate_rename_lessontime_period_and_more'),  # Укажите последнюю миграцию
    ]

    operations = [
        migrations.RunPython(convert_day_of_week),
    ]