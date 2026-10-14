from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('schedule_ingestion', '0008_alter_exportrevision_options')]
    operations = [
        migrations.AddField(model_name='parserun', name='sync_range', field=models.JSONField(blank=True, null=True)),
        migrations.AddField(model_name='parserun', name='force_refresh', field=models.BooleanField(default=False)),
        migrations.AddField(model_name='runsheet', name='selected', field=models.BooleanField(default=True)),
        migrations.AddField(model_name='runsheet', name='selection_reason', field=models.CharField(
            max_length=16, default='full', choices=[
                ('full', 'Полный разбор'), ('new', 'Ещё не опубликован'),
                ('changed', 'Контент изменился'), ('context', 'Изменились условия разбора'),
                ('range', 'Период ещё не обработан'), ('unchanged', 'Без изменений — пропущен')])),
    ]
