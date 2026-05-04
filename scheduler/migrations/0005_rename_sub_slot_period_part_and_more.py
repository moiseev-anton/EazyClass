from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ("scheduler", "0004_alter_period_unique_together_period_sub_slot_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="timing",
            old_name="half_duration_minutes",
            new_name="part_duration",
        ),
        migrations.AlterUniqueTogether(
            name="period",
            unique_together={("date", "lesson_number", "part")},
        ),
        migrations.AddField(
            model_name="period",
            name="part",
            field=models.PositiveSmallIntegerField(
                choices=[(0, "full"), (1, "1st part"), (2, "2nd part")], default=0
            ),
        ),
        migrations.RemoveField(
            model_name="period",
            name="sub_slot",
        ),
    ]
