import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Alias',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.TextField()),
                ('spelling', models.TextField()),
                ('target', models.TextField()),
                ('source', models.TextField()),
                ('identity_sha256', models.CharField(max_length=64, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='ArchiveFile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('path', models.TextField()),
                ('sha256', models.CharField(max_length=64)),
                ('imported_at', models.TextField()),
                ('identity_sha256', models.CharField(max_length=64, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='CatalogExclusionEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.TextField()),
                ('resource', models.CharField(max_length=64)),
                ('entity_id', models.BigIntegerField()),
                ('excluded', models.BooleanField()),
                ('reviewer', models.TextField()),
                ('reason', models.TextField()),
                ('recorded_at', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='CatalogSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.TextField()),
                ('resource', models.CharField(max_length=64)),
                ('fetched_at', models.TextField()),
                ('payload', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='CatalogSyncFailure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.TextField()),
                ('resource', models.CharField(max_length=64)),
                ('attempted_at', models.TextField()),
                ('error_type', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='Confirmation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('raw_cell', models.TextField()),
                ('raw_cell_sha256', models.CharField(db_index=True, max_length=64)),
                ('context', models.TextField()),
                ('output', models.TextField()),
                ('reviewer', models.TextField()),
                ('evidence', models.TextField()),
                ('confirmed_at', models.TextField()),
                ('identity_sha256', models.CharField(max_length=64, unique=True)),
            ],
        ),
        migrations.CreateModel(
            name='ConfirmationRevocation',
            fields=[
                ('correction', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, serialize=False, to='schedule_ingestion.confirmation')),
                ('reviewer', models.TextField()),
                ('reason', models.TextField()),
                ('revoked_at', models.TextField()),
            ],
        ),
        migrations.CreateModel(
            name='KnowledgeImport',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('source_sha256', models.CharField(blank=True, max_length=64)),
                ('source_path', models.TextField(blank=True)),
                ('imported_at', models.DateTimeField(null=True)),
                ('counts', models.JSONField(default=dict)),
            ],
            options={
                'constraints': [models.CheckConstraint(condition=models.Q(('id', 1)), name='ingestion_single_import')],
            },
        ),
        migrations.CreateModel(
            name='Observation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('raw_cell', models.TextField()),
                ('context', models.TextField()),
                ('output', models.TextField()),
                ('archive_records', models.TextField()),
                ('record_numbers', models.TextField()),
                ('label_status', models.CharField(default='unreviewed', max_length=16)),
                ('file', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='schedule_ingestion.archivefile')),
            ],
            options={
                'constraints': [models.CheckConstraint(condition=models.Q(('label_status', 'unreviewed')), name='ingestion_observation_unreviewed')],
            },
        ),
    ]
