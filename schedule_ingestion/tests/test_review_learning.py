import json
import uuid
from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from schedule_ingestion.inline_review import replace_batch
from schedule_ingestion.knowledge_reader import DjangoKnowledgeReader
from schedule_ingestion.models import ScheduleSource, Confirmation, ConfirmationRevocation, Publication
from schedule_ingestion.run_storage import record_inputs, save_export, load_export


class ReviewLearningTests(TestCase):
    def setUp(self):
        self.original = 'Инострaнный язык в пофессиональной деятельности'
        self.corrected = 'Иностранный язык в профессиональной деятельности'
        source = ScheduleSource.objects.create(name='Test', sheet_names=['2 курс'])
        self.run = record_inputs(source_id=source.pk, sheets={'2 курс': []},
            captured_at=timezone.now(), reference_date=date(2026, 10, 14),
            knowledge_as_of=timezone.now(), parser_manifest={'test': True})
        row = dict(sheet_name='2 курс', group='21 БАС', date='2026-10-15',
            lesson_number=2, part=0, subgroup=0, raw_cell=self.original,
            subject=self.original, teacher='Иванов И.И.', classroom='3208',
            review_status='needs_review', annotations=[], diagnostics=[],
            subject_proposal=json.dumps(dict(original=self.original,
                candidates=[dict(subject=self.corrected)], part=0, subgroup=0)))
        self.first = save_export(run_id=self.run.pk, expected_revision=0, request_id=uuid.uuid4(),
            groups=['21 БАС'], lessons=[row], review_items=[], author='parser')

    def edit(self, version, *, checked=True, subject=None, learn=True):
        payload = load_export(version.pk)
        data = dict(request_id=str(uuid.uuid4()), reason='Review', changes=[dict(index=0,
            rows=[dict(payload['lessons'][0], base_index=0, reviewed=checked,
                subject=subject or self.corrected, annotation='')])])
        changed = replace_batch(payload, data)
        params = dict(run_id=self.run.pk, expected_revision=version.number,
            request_id=data['request_id'], author='admin', learn_confirmed=learn, **changed)
        return save_export(**params), params

    def test_saved_confirmation_drives_future_subject_reuse_without_publication(self):
        version, params = self.edit(self.first)
        self.assertFalse(Publication.objects.exists())
        self.assertEqual(Confirmation.objects.count(), 1)
        self.assertEqual(save_export(**params).pk, version.pk)
        self.assertEqual(Confirmation.objects.count(), 1)
        from verified_subject_reuse import choose
        feedback = DjangoKnowledgeReader().subject_feedback(as_of=timezone.now())
        context = dict(sheet_name='2 курс', group='21 БАС', date='2026-10-22', lesson_number='2')
        # Same production reuse rule; a new occurrence must use the accepted candidate.
        class Policy:
            distinct = set()
            targets = {}
        result = choose(feedback, self.original, context, Policy())
        self.assertEqual(result['subject'], self.corrected)
        self.assertEqual(result['confirmation_ids'], [Confirmation.objects.get().pk])

    def test_unchecked_and_automatic_exports_do_not_confirm(self):
        version, _ = self.edit(self.first, checked=False)
        self.assertFalse(Confirmation.objects.exists())
        self.edit(version, learn=False)
        self.assertFalse(Confirmation.objects.exists())

    def test_revised_confirmation_revokes_old_output(self):
        version, _ = self.edit(self.first)
        self.edit(version, subject='Другой предмет')
        self.assertEqual(ConfirmationRevocation.objects.count(), 1)
        result = DjangoKnowledgeReader().lookup_applicable(self.original,
            dict(sheet_name='2 курс', group='21 БАС', date='2026-10-15', lesson_number='2'))
        self.assertEqual(result['status'], 'confirmed')
        self.assertEqual(result['lessons'][0]['subject'], 'Другой предмет')

    def test_confirmation_failure_rolls_back_revision(self):
        with patch('schedule_ingestion.review_learning.Confirmation.objects') as objects:
            objects.using.return_value.filter.return_value = []
            objects.using.return_value.create.side_effect = RuntimeError('failure')
            with self.assertRaises(RuntimeError):
                self.edit(self.first)
        self.run.refresh_from_db()
        self.assertEqual(self.run.head_revision, 1)
        self.assertEqual(self.run.exports.count(), 1)

    def test_partial_card_confirmation_does_not_train(self):
        payload = load_export(self.first.pk)
        data = dict(request_id=str(uuid.uuid4()), reason='Split', changes=[dict(index=0,
            rows=[dict(payload['lessons'][0], base_index=0, subgroup=1,
                       reviewed=True, annotation=''),
                  dict(payload['lessons'][0], base_index=None, subgroup=2,
                       reviewed=False, annotation='')])])
        changed = replace_batch(payload, data)
        save_export(run_id=self.run.pk, expected_revision=1, request_id=data['request_id'],
            author='admin', learn_confirmed=True, **changed)
        self.assertFalse(Confirmation.objects.exists())

    def test_teacher_confirmation_is_available_to_existing_reader(self):
        version, _ = self.edit(self.first)
        payload = load_export(version.pk)
        data = dict(request_id=str(uuid.uuid4()), reason='Teacher', changes=[dict(index=0,
            rows=[dict(payload['lessons'][0], base_index=0, reviewed=True,
                       teacher='Петров П.П.', annotation='')])])
        changed = replace_batch(payload, data)
        save_export(run_id=self.run.pk, expected_revision=2, request_id=data['request_id'],
            author='admin', learn_confirmed=True, **changed)
        result = DjangoKnowledgeReader().lookup_applicable(self.original,
            dict(sheet_name='2 курс', group='21 БАС', date='2026-10-15', lesson_number='2'))
        self.assertEqual(result['lessons'][0]['teacher'], 'Петров П.П.')
