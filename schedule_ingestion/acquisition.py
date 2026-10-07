"""Fetch the complete source before storing any successful run."""
from copy import deepcopy
import uuid

from django.utils import timezone

from .models import ScheduleSource, ParseRun
from .google_sheets import fetch_sheet
from .parser_runtime import runtime_manifest
from .run_storage import record_inputs


def acquire_source(source_id, *, acquisition_id, resource_root, catalog_source, using='default'):
    acquisition_id = uuid.UUID(str(acquisition_id))
    previous = ParseRun.objects.using(using).filter(acquisition_id=acquisition_id).first()
    if previous:
        if previous.source_id != source_id:
            raise ValueError('Acquisition ID belongs to another source')
        return previous
    source = ScheduleSource.objects.using(using).get(pk=source_id)
    configuration = deepcopy(dict(spreadsheet_id=source.spreadsheet_id,
                                  sheet_names=source.sheet_names, sheet_gids=source.sheet_gids))
    names, gids = configuration['sheet_names'], configuration['sheet_gids']
    if (not source.enabled or not isinstance(names, list) or not names or
            any(not isinstance(name, str) or not name.strip() or len(name) > 200 for name in names) or
            len(names) != len(set(names)) or not isinstance(gids, dict) or set(gids) != set(names) or
            any(type(gid) is not int or gid < 0 for gid in gids.values()) or
            len(set(gids.values())) != len(gids)):
        raise ValueError('An enabled source with distinct sheet names and gids is required')
    manifest = runtime_manifest(resource_root, catalog_source=catalog_source)
    started_at = timezone.now()
    rows = {name: fetch_sheet(configuration['spreadsheet_id'], gids[name]) for name in names}
    return record_inputs(source_id=source.pk, sheets=rows, captured_at=started_at,
        reference_date=timezone.localtime(started_at).date(), knowledge_as_of=started_at,
        parser_manifest=manifest, expected_configuration=configuration,
        acquisition_id=acquisition_id, using=using)
