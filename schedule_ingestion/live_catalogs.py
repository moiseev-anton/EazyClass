"""Read all Django catalog entries once per parse; never persist catalog copies."""
from copy import deepcopy

from django.db import connections, transaction
from django.utils import timezone

from .historical_catalogs import HistoricalCatalogReader

SUPPLEMENT_SOURCE = 'local:owner-provided-teachers'


def load_live_catalogs(*, source, using='default'):
    """source identifies the EazyClass origin of imported exclusion decisions.

    Read one consistent PostgreSQL state into memory, including inactive rows.
    Historical API catalogs are deliberately not consulted. Only the owner's
    local teacher supplement and explicit exclusion decisions are retained.
    """
    from scheduler.models import Teacher, Classroom

    source = source.strip().rstrip('/')
    if not source or source == SUPPLEMENT_SOURCE:
        raise ValueError('An explicit EazyClass catalog source is required')
    connection = connections[using]
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ValueError('Catalog loading must start outside an existing transaction')
    if connection.vendor not in ('postgresql', 'sqlite'):
        raise ValueError('Unsupported catalog database')
    with transaction.atomic(using=using):
        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        stamp = timezone.now().isoformat()
        history = HistoricalCatalogReader(using=using)
        catalogs = {}
        for resource, model, fields, order in (
            ('teachers', Teacher, ('id', 'full_name', 'short_name', 'endpoint'), 'full_name'),
            ('classrooms', Classroom, ('id', 'title'), 'title'),
        ):
            items, provenance = [], {}
            for row in model.objects.using(using).order_by(order, 'pk').values(*fields, 'is_active'):
                active = row.pop('is_active')
                if row['id'] <= 0:
                    raise ValueError('EazyClass catalog IDs must be positive')
                display = row['short_name'] if resource == 'teachers' else row['title']
                if not display.strip():
                    raise ValueError('Missing catalog display name')
                items.append(row)
                provenance[row['id']] = dict(origin='django', is_active=active,
                    present_in_database=True, present_in_latest=True)
            if not items:
                raise ValueError('Empty catalog: ' + resource)
            catalogs[resource] = dict(
                data=dict(id=None, fetched_at=stamp, items=items, provenance=provenance),
                exclusions=history.catalog_exclusions(source, resource))
        supplement = dict(
            data=history.load_catalog(SUPPLEMENT_SOURCE, 'teachers'),
            exclusions=history.catalog_exclusions(SUPPLEMENT_SOURCE, 'teachers'))
    return LiveCatalogReader(source=source, catalogs=catalogs, supplement=supplement)


class LiveCatalogReader:
    """In-memory input for existing parser repositories; no DB calls or writes."""
    def __init__(self, *, source, catalogs, supplement):
        self.source = source
        self._catalogs = deepcopy(catalogs)
        self._supplement = deepcopy(supplement)

    def _section(self, source, resource):
        if source.rstrip('/') == self.source:
            return self._catalogs.get(resource)
        if source == SUPPLEMENT_SOURCE and resource == 'teachers':
            return self._supplement
        return None

    def load_catalog(self, source, resource):
        section = self._section(source, resource)
        return deepcopy(section['data']) if section else None

    def load_accumulated_catalog(self, source, resource):
        # Repository compatibility only: this returns current DB rows, no history.
        if source.rstrip('/') != self.source:
            return None
        return self.load_catalog(source, resource)

    def catalog_exclusions(self, source, resource):
        section = self._section(source, resource)
        return deepcopy(section['exclusions']) if section else {}

    def parser_services(self):
        # Deferred: Django startup and migrations do not require the parser wheel.
        from repositories import TeacherRepository, ClassroomRepository
        from services import TeacherService, ClassroomService
        teachers = TeacherRepository(store=self, source=self.source)
        classrooms = ClassroomRepository(store=self, source=self.source)
        if not teachers.load_local() or not classrooms.load_local():
            raise ValueError('Incomplete catalogs')
        return TeacherService(teachers), ClassroomService(classrooms)
