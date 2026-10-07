"""Historical imported catalogs for reproduction, not the live EazyClass catalog."""
import json
from .models import CatalogSnapshot, CatalogExclusionEvent


class HistoricalCatalogReader:
    def __init__(self, *, using='default'):
        self.using = using

    def load_catalog(self, source, resource):
        row = CatalogSnapshot.objects.using(self.using).filter(source=source, resource=resource).order_by('-id').values().first()
        return dict(row, items=json.loads(row['payload'])) if row else None

    def load_accumulated_catalog(self, source, resource):
        rows = list(CatalogSnapshot.objects.using(self.using).filter(source=source, resource=resource).order_by('id').values())
        if not rows:
            return None
        items, provenance = {}, {}
        for row in rows:
            for item in json.loads(row['payload']):
                key = item['id']
                if key not in provenance:
                    provenance[key] = dict(first_snapshot_id=row['id'], first_seen=row['fetched_at'])
                items[key] = item
                provenance[key].update(last_snapshot_id=row['id'], last_seen=row['fetched_at'])
        latest = rows[-1]
        present = {item['id'] for item in json.loads(latest['payload'])}
        for key, info in provenance.items():
            info['present_in_latest'] = key in present
        return dict(id=latest['id'], fetched_at=latest['fetched_at'], items=list(items.values()), provenance=provenance)

    def catalog_exclusions(self, source, resource):
        latest = {}
        for row in CatalogExclusionEvent.objects.using(self.using).filter(
                source=source.rstrip('/'), resource=resource).order_by('id').values():
            row['excluded'] = int(row['excluded'])
            latest[row['entity_id']] = row
        return {key: row for key, row in latest.items() if row['excluded']}
