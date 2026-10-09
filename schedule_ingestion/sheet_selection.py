"""Select inputs against applied publications, never against mere downloads."""
import json

from django.db.models import Prefetch

from scheduler.dtos.lesson_sync_range import LessonSyncRange
from .models import Publication, RunSheet


def sheet_identity(configuration, name):
    # Legacy captures without gids cannot establish a reusable sheet identity.
    gid = configuration.get('sheet_gids', {}).get(name)
    if type(gid) is not int:
        return None
    return configuration['spreadsheet_id'], gid


def select_sheets(*, source_id, configuration, hashes, reference_date, manifest,
                  resolved_range=None, force=False, using='default'):
    reason = RunSheet.Selection
    if resolved_range is None or force:
        return {name: reason.FULL for name in hashes}
    bounds = LessonSyncRange.from_dict(resolved_range)
    remaining = {sheet_identity(configuration, name): name for name in hashes}
    remaining.pop(None, None)
    result = {name: reason.NEW for name in hashes}
    # The latest APPLIED publication wins, including manual review corrections.
    # Never reuse an older matching hash after an intervening different version.
    publications = (Publication.objects.using(using)
        .filter(revision__run__source_id=source_id, status='applied', applied_at__isnull=False)
        .select_related('revision__run').order_by('-applied_at', '-requested_at', '-pk')
        .defer('prepared_payload', 'summary', 'revision__payload')
        .prefetch_related(Prefetch('revision__run__sheets',
            queryset=RunSheet.objects.using(using).filter(selected=True))))
    for publication in publications.iterator(chunk_size=100):
        run = publication.revision.run
        old_configuration = json.loads(run.source_configuration)
        for sheet in run.sheets.all():
            identity = sheet_identity(old_configuration, sheet.name)
            name = remaining.pop(identity, None)
            if name is None:
                continue
            if sheet.content_id != hashes[name]:
                result[name] = reason.CHANGED
            elif (sheet.name != name or run.parser_manifest != manifest
                  or run.reference_date.year != reference_date.year):
                result[name] = reason.CONTEXT
            elif (publication.start_date > bounds.start
                  or (publication.end_date is not None
                      and (bounds.end is None or publication.end_date < bounds.end))):
                result[name] = reason.RANGE
            else:
                result[name] = reason.UNCHANGED
        if not remaining:
            break
    return result
