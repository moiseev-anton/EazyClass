"""Atomic edits of all lessons originating from one input cell."""
from copy import deepcopy
import hashlib
import json
import uuid

from .admin_forms import LessonReviewForm


def identity(row, index):
    if row.get('review_cell_id'):
        return ('id', row['review_cell_id'])
    if not row.get('raw_cell'):
        return ('row', index)
    return tuple(row.get(k) for k in ('sheet_name', 'group', 'date', 'lesson_number', 'raw_cell'))


def cell_indices(rows, index):
    key = identity(rows[index], index)
    return [i for i, row in enumerate(rows) if identity(row, i) == key]


def review_state(payload):
    cards = {}
    for index, row in enumerate(payload['lessons']):
        key = identity(row, index)
        card = cards.setdefault(key, {'index': index, 'indices': [], 'rows': []})
        card['indices'].append(index)
        card['rows'].append(row)
    return {'groups': payload['groups'], 'cards': list(cards.values())}


def restore_review_origin(payload, initial):
    """Recover provenance for older exports when the source cell still matches exactly."""
    def source_key(row):
        return tuple(row.get(k) for k in ('sheet_name', 'group', 'date', 'lesson_number', 'raw_cell'))
    sources = {}
    for row in initial['lessons']:
        if row.get('raw_cell'):
            sources.setdefault(source_key(row), []).append(row)
    for card in review_state(payload)['cards']:
        rows = card['rows']
        if any('review_original_rows' in row for row in rows):
            continue
        before = sources.get(source_key(rows[0]))
        if not before:
            continue
        fields = ('group', 'date', 'lesson_number', 'part', 'subgroup', 'subject',
                  'teacher', 'classroom', 'annotation', 'annotations', 'review_status')
        changed = [[row.get(k) for k in fields] for row in rows] != [
            [row.get(k) for k in fields] for row in before]
        required = any(row.get('review_status') == 'needs_review' for row in before)
        for row in rows:
            row['review_required'] = required
            if changed:
                row['review_original_rows'] = deepcopy(before)
                row['review_applied'] = True
    return payload


def replace_batch(payload, data):
    if not isinstance(data, dict) or not isinstance(data.get('changes'), list) or not data['changes']:
        raise ValueError('Нет изменений для сохранения.')
    request_id = uuid.UUID(str(data['request_id']))
    replacements, excluded, additions = {}, set(), []
    for number, change in enumerate(data['changes']):
        if not isinstance(change, dict):
            raise ValueError('Некорректная карточка.')
        index = change.get('index')
        child = dict(change, request_id=str(uuid.uuid5(request_id, str(number))), reason=data['reason'])
        if index is None:
            if any(row.get('base_index') is not None for row in child['rows']):
                raise ValueError('Новое занятие не может ссылаться на существующую запись.')
            child['rows'] = [dict(row, reviewed=True) for row in child['rows']]
            empty = dict(payload, lessons=[{}])
            additions.extend(replace_cell(empty, [0], child)['lessons'])
            continue
        if type(index) is not int or index < 0 or index >= len(payload['lessons']):
            raise ValueError('Исходная карточка не найдена.')
        indices = cell_indices(payload['lessons'], index)
        if excluded.intersection(indices):
            raise ValueError('Одна карточка передана несколько раз.')
        edited = replace_cell(payload, indices, child)
        replacements[indices[0]] = edited['lessons'][indices[0]:indices[0] + len(child['rows'])]
        excluded.update(indices)
    result = deepcopy(payload)
    result['lessons'] = []
    for index, row in enumerate(payload['lessons']):
        result['lessons'].extend(replacements.get(index, []))
        if index not in excluded:
            result['lessons'].append(row)
    result['lessons'].extend(additions)
    return result


def replace_cell(payload, indices, data):
    from schedule_csv import annotation_text
    if not isinstance(data, dict) or not isinstance(data.get('rows'), list) or len(data['rows']) > 100:
        raise ValueError('Ожидается список, не более 100 занятий в ячейке.')
    if not isinstance(data.get('reason'), str) or not data['reason'].strip():
        raise ValueError('Укажите причину изменения.')
    originals = payload['lessons']
    first = originals[indices[0]]
    before_review = first.get('review_original_rows')
    if before_review is None:
        before_review = [{k: deepcopy(v) for k, v in originals[i].items()
                          if k not in ('review_original_rows',)} for i in indices]
    required_review = any(row.get('review_required', row.get('review_status') == 'needs_review')
                          for row in before_review)
    replacements, seen, slots = [], set(), set()
    cell_id = originals[indices[0]].get('review_cell_id') or hashlib.sha256(
        json.dumps([data['request_id'], identity(originals[indices[0]], indices[0])], ensure_ascii=False).encode()).hexdigest()[:20]
    for number, entry in enumerate(data['rows'], 1):
        if not isinstance(entry, dict):
            raise ValueError('Некорректное занятие.')
        base_index = entry.get('base_index')
        if base_index is not None:
            if type(base_index) is not int or base_index not in indices or base_index in seen:
                raise ValueError('Исходная запись не принадлежит этой ячейке или повторяется.')
            seen.add(base_index)
        row = deepcopy(originals[base_index if base_index is not None else indices[0]])
        form = LessonReviewForm(dict(entry, request_id=data['request_id'], reason=data['reason']), groups=payload['groups'])
        if not form.is_valid():
            raise ValueError(f'Занятие {number}: ' + '; '.join(f'{key}: {", ".join(errors)}' for key, errors in form.errors.items()))
        cleaned = form.cleaned_data
        for key in ('group', 'lesson_number', 'part', 'subgroup', 'subject', 'teacher', 'classroom'):
            row[key] = cleaned[key]
        row.update(date=cleaned['date'].isoformat(), review_cell_id=cell_id,
                   review_original_rows=before_review, review_required=required_review,
                   review_applied=True,
                   review_status='reviewed' if cleaned['reviewed'] else 'needs_review')
        old_annotation = annotation_text(row['annotations']) if 'annotations' in row else row.get('annotation', '')
        if cleaned['annotation'] != (old_annotation or ''):
            row.pop('annotations', None)
            row['annotation'] = cleaned['annotation']
        slot = tuple(row[key] for key in ('group', 'date', 'lesson_number', 'part', 'subgroup'))
        if slot in slots:
            raise ValueError('Повторяется сочетание даты, группы, пары, части и подгруппы.')
        slots.add(slot)
        replacements.append(row)
    result = deepcopy(payload)
    result['lessons'] = []
    for i, row in enumerate(originals):
        if i == indices[0]:
            result['lessons'].extend(replacements)
        if i not in indices:
            result['lessons'].append(row)
    return result
