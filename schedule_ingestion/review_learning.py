"""Persist explicit human confirmations using the local CSV review evidence format."""
import json

from django.utils import timezone

from .inline_review import review_state
from .knowledge_import import model_values
from .models import Confirmation, ConfirmationRevocation, KnowledgeImport


def learn_review(revision, previous, payload, *, using):
    from knowledge_store import encode
    from review_queue import CONTEXT_FIELDS
    from csv_review import lessons
    from subject_feedback import classify
    from schedule_csv import annotation_text

    # Serialize confirmation replacement across independently reviewed exports.
    KnowledgeImport.objects.using(using).get_or_create(pk=1)
    KnowledgeImport.objects.using(using).select_for_update().get(pk=1)
    previous_cards = [card['rows'] for card in review_state(previous)['cards']]
    for card in review_state(payload)['cards']:
        rows = card['rows']
        if rows in previous_cards or not all(row.get('review_status') == 'reviewed' for row in rows):
            continue
        original = rows[0].get('review_original_rows')
        if not original or not original[0].get('raw_cell'):
            continue
        raw = original[0]['raw_cell']
        context = {key: str(original[0].get(key, '')) for key in CONTEXT_FIELDS}
        if not all(all(str(row.get(key, '')) == value for key, value in context.items())
                   and row.get('raw_cell') == raw for row in [*original, *rows]):
            # Like local CSV review, moving a lesson is not a parser correction.
            continue

        def output(items):
            converted = []
            for row in items:
                notes = row.get('annotations', [])
                converted.append({
                    **{key: str(row.get(key) or '') for key in
                       ('subject', 'teacher', 'classroom', 'part', 'subgroup')},
                    'annotations': encode(notes),
                    'annotation': row.get('annotation', annotation_text(notes)),
                    'diagnostics': encode(row.get('diagnostics', [])),
                })
            return lessons(converted)

        before, after = output(original), output(rows)
        desired = encode(sorted(after, key=encode))
        active = list(Confirmation.objects.using(using).filter(
            raw_cell=raw, confirmationrevocation__isnull=True))
        revoke = []
        for old in active:
            scope = json.loads(old.context)
            if not all(context.get(key, '') == str(value) for key, value in scope.items()):
                continue
            if old.output != desired:
                if scope != context:
                    raise ValueError('Исправление конфликтует с более широким подтверждением парсера.')
                revoke.append(old.pk)
        proposals = [row['subject_proposal'] for row in original if row.get('subject_proposal')]
        feedback = classify(proposals, after)
        slots = lambda items: sorted((r['part'], r['subgroup']) for r in items)
        if slots(before) != slots(after):
            for item in feedback:
                item['status'] = 'unresolved_structure'
        evidence = f'CSV review {revision.pk}; replaces={revoke}; Явное подтверждение в EazyClass'
        for name, values in (
            ('teacher_proposals', [{k: row.get(k, '') for k in (
                'teacher_original', 'suggested_teacher', 'teacher_proposal_applied',
                'teacher_proposal_policy', 'teacher_model_sha256', 'teacher_history_policy',
                'teacher_history_sha256', 'teacher_history_confirmation_ids')}
                for row in original if row.get('suggested_teacher')]),
            ('prior_confirmation_ids', [r['prior_confirmation_ids'] for r in original if r.get('prior_confirmation_ids')]),
            ('extraction_proposals', [{k: row.get(k, '') for k in (
                'extraction_original', 'extraction_model_sha256', 'extraction_proposal_policy',
                'extraction_proposal_reason')} for row in original if row.get('extraction_model_sha256')]),
            ('classroom_proposals', [r['classroom_proposal'] for r in original if r.get('classroom_proposal')]),
            ('subject_proposals', proposals), ('subject_feedback', feedback),
        ):
            evidence += '; ' + name + '=' + encode(values)
        now = timezone.now().isoformat()
        values = model_values('confirmed_corrections', dict(raw_cell=raw, context=encode(context),
            output=desired, reviewer=revision.author, evidence=evidence, confirmed_at=now))
        Confirmation.objects.using(using).create(**values)
        for pk in revoke:
            ConfirmationRevocation.objects.using(using).create(correction_id=pk,
                reviewer=revision.author, reason=evidence, revoked_at=now)
