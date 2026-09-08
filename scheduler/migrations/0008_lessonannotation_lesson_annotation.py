import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('scheduler', '0007_broadcast'),
    ]

    operations = [
        migrations.CreateModel(
            name='LessonAnnotation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255, unique=True)),
            ],
            options={
                'verbose_name': 'Lesson annotation',
                'verbose_name_plural': 'Lesson annotations',
            },
        ),
        migrations.AddField(
            model_name='lesson',
            name='annotation',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='lessons', to='scheduler.lessonannotation'),
        ),
    ]
