"""Django implementation of TableParser's read contract (no SQLite connection)."""
import json
from collections import defaultdict
from datetime import datetime

from django.db.models import F

from .models import Confirmation, Observation
from .knowledge_import import raw_hash


class DjangoKnowledgeReader:
    def __init__(self, *, using='default'):
        self.using = using

    def _active(self):
        return Confirmation.objects.using(self.using).filter(confirmationrevocation__isnull=True)

    def _raw_confirmations(self, raw_cell):
        rows = list(self._active().filter(raw_cell_sha256=raw_hash(raw_cell), raw_cell=raw_cell).values(
            'id', 'context', 'output', 'reviewer', 'evidence'))
        # The old SQLite covering unique index orders these equal-raw queries
        # by the remaining identity fields. Sort in Python to avoid PG collation.
        return sorted(rows, key=lambda row: tuple(row[k] for k in ('context', 'output', 'reviewer', 'evidence')))

    def subject_names(self):
        from lesson_annotations import extract_annotations
        subjects = set()
        for output in Observation.objects.using(self.using).values_list('output', flat=True).distinct():
            for lesson in json.loads(output):
                subject, _, _ = extract_annotations(lesson.get('subject') or '')
                if subject:
                    subjects.add(subject)
        return frozenset(subjects)

    def lookup_applicable(self, raw_cell, context):
        rows = [row for row in self._raw_confirmations(raw_cell) if all(
            str(context.get(key, '')) == str(value) for key, value in json.loads(row['context']).items())]
        outputs = {row['output'] for row in rows}
        return dict(status='conflict' if len(outputs) > 1 else 'confirmed' if outputs else 'missing',
                    lessons=json.loads(next(iter(outputs))) if len(outputs) == 1 else None,
                    correction_ids=[row['id'] for row in rows])

    def repeated_confirmation(self, raw_cell, context):
        rows = [row for row in self._raw_confirmations(raw_cell) if all(
            str(json.loads(row['context']).get(key, '')) == str(context.get(key, ''))
            for key in ('sheet_name', 'group'))]
        outputs = {row['output'] for row in rows}
        if len(outputs) != 1:
            return None
        lessons = json.loads(next(iter(outputs)))
        if len(lessons) != 1:
            return None
        return dict(lessons=lessons, correction_ids=[row['id'] for row in rows])

    def verified_records(self, *, as_of):
        if as_of.utcoffset() is None:
            raise ValueError('as_of must include timezone')
        rows = self._active().order_by('id').values('id', 'raw_cell', 'context', 'output', 'confirmed_at')
        return [dict(row, context=json.loads(row['context']), output=json.loads(row['output']))
                for row in rows if datetime.fromisoformat(row['confirmed_at']) <= as_of]

    def teacher_records(self):
        rows = Confirmation.objects.using(self.using).order_by('id').values(
            'id', 'raw_cell', 'context', 'output', 'reviewer', 'evidence', 'confirmed_at',
            revoked_at=F('confirmationrevocation__revoked_at'))
        return [dict(row, context=json.loads(row['context']), output=json.loads(row['output'])) for row in rows]

    def subject_index(self, swaps):
        from subject_candidates import SubjectIndex, clean_index
        entries = defaultdict(lambda: defaultdict(set))
        for name, rows in (
            ('observations', Observation.objects.using(self.using).order_by('id').values_list('id', 'output')),
            ('confirmations', self._active().order_by('id').values_list('id', 'output')),
        ):
            for ident, output in rows:
                for lesson in json.loads(output):
                    if lesson.get('subject'):
                        entries[lesson['subject']][name].add(ident)
        aliases = swaps.get('subjects', {})
        for source, target in aliases.items():
            entries[source]['alias_sources'].add(source)
            entries[target]['alias_targets'].add(source)
        index = SubjectIndex({name: {key: sorted(ids) for key, ids in sources.items()}
                              for name, sources in entries.items()}, aliases)
        return clean_index(index)[0]

    def subject_feedback(self, *, as_of):
        from subject_feedback import extract
        if as_of is None or as_of.utcoffset() is None:
            raise ValueError('as_of must include timezone')
        index = defaultdict(list)
        for row in self.teacher_records():
            if row['revoked_at'] and datetime.fromisoformat(row['revoked_at']) <= as_of:
                continue
            if datetime.fromisoformat(row['confirmed_at']) > as_of:
                continue
            context = row['context']
            if not context.get('group') or not context.get('sheet_name'):
                continue
            for feedback in extract(row['evidence'], row['output']):
                if feedback.get('original'):
                    index[(context['sheet_name'], context['group'], feedback['original'])].append(
                        dict(feedback, context=context, confirmation_id=row['id']))
        return dict(index)
