"""Parser memory, separate from schedule rows and publication state.

Historical JSON and timestamps intentionally remain exact text: their original
representations participate in parser evidence hashes and conflict detection.
"""
import uuid

from django.db import models


class CatalogSnapshot(models.Model):
    source = models.TextField()
    resource = models.CharField(max_length=64)
    fetched_at = models.TextField()
    payload = models.TextField()


class CatalogSyncFailure(models.Model):
    source = models.TextField()
    resource = models.CharField(max_length=64)
    attempted_at = models.TextField()
    error_type = models.TextField()


class ArchiveFile(models.Model):
    path = models.TextField()
    sha256 = models.CharField(max_length=64)
    imported_at = models.TextField()
    identity_sha256 = models.CharField(max_length=64, unique=True)


class Observation(models.Model):
    file = models.ForeignKey(ArchiveFile, on_delete=models.PROTECT)
    raw_cell = models.TextField()
    context = models.TextField()
    output = models.TextField()
    archive_records = models.TextField()
    record_numbers = models.TextField()
    label_status = models.CharField(max_length=16, default="unreviewed")

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(label_status="unreviewed"),
                                              name="ingestion_observation_unreviewed")]


class Alias(models.Model):
    kind = models.TextField()
    spelling = models.TextField()
    target = models.TextField()
    source = models.TextField()
    identity_sha256 = models.CharField(max_length=64, unique=True)


class Confirmation(models.Model):
    raw_cell = models.TextField()
    raw_cell_sha256 = models.CharField(max_length=64, db_index=True)
    context = models.TextField()
    output = models.TextField()
    reviewer = models.TextField()
    evidence = models.TextField()
    confirmed_at = models.TextField()
    identity_sha256 = models.CharField(max_length=64, unique=True)


class ConfirmationRevocation(models.Model):
    correction = models.OneToOneField(Confirmation, primary_key=True, on_delete=models.PROTECT)
    reviewer = models.TextField()
    reason = models.TextField()
    revoked_at = models.TextField()


class CatalogExclusionEvent(models.Model):
    source = models.TextField()
    resource = models.CharField(max_length=64)
    entity_id = models.BigIntegerField()
    excluded = models.BooleanField()
    reviewer = models.TextField()
    reason = models.TextField()
    recorded_at = models.TextField()


class KnowledgeImport(models.Model):
    """A singleton guards initial import; never overwrite working knowledge."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    source_sha256 = models.CharField(max_length=64, blank=True)
    source_path = models.TextField(blank=True)
    imported_at = models.DateTimeField(null=True)
    counts = models.JSONField(default=dict)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="ingestion_single_import")]


class ScheduleSource(models.Model):
    name = models.CharField(max_length=200)
    spreadsheet_id = models.CharField(max_length=200)
    sheet_names = models.JSONField(default=list)
    sheet_gids = models.JSONField(default=dict)
    enabled = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class ImmutableRecord(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError('Create a new version instead of editing stored data')
        return super().save(*args, **kwargs)


class SheetContent(ImmutableRecord):
    sha256 = models.CharField(max_length=64, primary_key=True)
    payload = models.TextField()


class ParseRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(ScheduleSource, on_delete=models.PROTECT)
    acquisition_id = models.UUIDField(null=True, unique=True, editable=False)
    source_configuration = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    captured_at = models.DateTimeField()
    reference_date = models.DateField()
    knowledge_as_of = models.DateTimeField()
    parser_manifest = models.TextField()
    head_revision = models.PositiveIntegerField(default=0)


class RunSheet(ImmutableRecord):
    run = models.ForeignKey(ParseRun, on_delete=models.PROTECT, related_name='sheets')
    name = models.CharField(max_length=200)
    position = models.PositiveIntegerField()
    content = models.ForeignKey(SheetContent, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['run', 'name'], name='ingestion_run_sheet_name'),
            models.UniqueConstraint(fields=['run', 'position'], name='ingestion_run_sheet_position'),
        ]


class ExportRevision(ImmutableRecord):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ParseRun, on_delete=models.PROTECT, related_name='exports')
    number = models.PositiveIntegerField()
    request_id = models.UUIDField()
    created_at = models.DateTimeField(auto_now_add=True)
    author = models.TextField()
    reason = models.TextField(blank=True)
    payload = models.TextField()
    sha256 = models.CharField(max_length=64)

    class Meta:
        permissions = [('review_export', 'Can review a parser export'),
                       ('publish_export', 'Can publish a parser export')]
        constraints = [
            models.UniqueConstraint(fields=['run', 'number'], name='ingestion_export_number'),
            models.UniqueConstraint(fields=['run', 'request_id'], name='ingestion_export_request'),
            models.CheckConstraint(condition=models.Q(number__gt=0), name='ingestion_export_positive'),
        ]


class ParseAttempt(models.Model):
    class Status(models.TextChoices):
        RUNNING = 'running'
        SUCCEEDED = 'succeeded'
        FAILED = 'failed'
        ABANDONED = 'abandoned'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(ParseRun, on_delete=models.PROTECT, related_name='attempts')
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    error_type = models.CharField(max_length=200, blank=True)
    export = models.ForeignKey(ExportRevision, on_delete=models.PROTECT, null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['run'], condition=models.Q(status='running'),
                                               name='ingestion_one_running_parse')]


class ScheduleWriteEvent(models.Model):
    group_ids = models.JSONField()
    start_date = models.DateField()
    end_date = models.DateField(null=True)
    observed_at = models.DateTimeField(db_index=True)


class Publication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    revision = models.ForeignKey(ExportRevision, on_delete=models.PROTECT)
    automatic = models.BooleanField(default=False)
    requested_by = models.TextField()
    requested_at = models.DateTimeField(auto_now_add=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True)
    # Prepared group IDs and values are fixed before queueing/review approval.
    prepared_payload = models.TextField()
    prepared_sha256 = models.CharField(max_length=64)
    status = models.CharField(max_length=16, default='pending')
    applied_at = models.DateTimeField(null=True)
    summary = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(status__in=['pending', 'applied', 'superseded']),
                                   name='ingestion_publication_status'),
            models.CheckConstraint(condition=models.Q(end_date__isnull=True) | models.Q(end_date__gte=models.F('start_date')),
                                   name='ingestion_publication_range'),
        ]


class PublicationDelivery(models.Model):
    publication = models.ForeignKey(Publication, on_delete=models.PROTECT, related_name='deliveries')
    phase = models.CharField(max_length=16)
    status = models.CharField(max_length=16, default='pending')
    token = models.UUIDField(null=True)
    started_at = models.DateTimeField(null=True)
    finished_at = models.DateTimeField(null=True)
    result = models.JSONField(default=dict)
    error_type = models.CharField(max_length=200, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['publication', 'phase'], name='ingestion_delivery_phase'),
            models.CheckConstraint(condition=models.Q(phase__in=['notifications', 'report']), name='ingestion_delivery_phase_valid'),
            models.CheckConstraint(condition=models.Q(status__in=['pending', 'sending', 'completed', 'uncertain', 'skipped']),
                                   name='ingestion_delivery_status'),
        ]


class DeliveryResolution(ImmutableRecord):
    id = models.UUIDField(primary_key=True, editable=False)
    delivery = models.ForeignKey(PublicationDelivery, on_delete=models.PROTECT, related_name='resolutions')
    created_at = models.DateTimeField(auto_now_add=True)
    decision = models.CharField(max_length=16)
    actor = models.TextField()
    reason = models.TextField()
    worker_stopped = models.BooleanField(default=False)
    previous = models.JSONField()

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(decision__in=['retry', 'skip']),
                                              name='ingestion_resolution_decision')]
