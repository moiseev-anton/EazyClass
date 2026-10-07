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
