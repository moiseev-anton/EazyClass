import json

from django import forms

from .models import ScheduleSource


class SourceForm(forms.ModelForm):
    class Meta:
        model = ScheduleSource
        fields = '__all__'
        help_texts = {
            'spreadsheet_id': 'Часть адреса Google Sheets между /d/ и /edit; не полный URL.',
            'sheet_names': 'JSON-список названий, например ["1 курс", "2 курс"].',
            'sheet_gids': 'JSON-карта gid из адресов вкладок, например {"1 курс": 0, "2 курс": 123456}.',
        }

    def clean(self):
        data = super().clean()
        names, gids = data.get('sheet_names'), data.get('sheet_gids')
        if (not isinstance(names, list) or not names or
                any(not isinstance(n, str) or not n.strip() or len(n) > 200 for n in names) or
                len(set(names)) != len(names)):
            raise forms.ValidationError('Укажите непустой список уникальных названий листов.')
        if (not isinstance(gids, dict) or set(gids) != set(names) or
                any(type(g) is not int or g < 0 for g in gids.values()) or
                len(set(gids.values())) != len(gids)):
            raise forms.ValidationError('Каждому листу должен соответствовать уникальный целый gid ≥ 0.')
        return data


class LessonReviewForm(forms.Form):
    request_id = forms.UUIDField(widget=forms.HiddenInput)
    group = forms.ChoiceField(label='Группа')
    date = forms.DateField(label='Дата', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    lesson_number = forms.IntegerField(label='Номер пары', min_value=1)
    part = forms.TypedChoiceField(label='Часть пары', coerce=int, choices=[(0, 'Целая'), (1, 'Первая'), (2, 'Вторая')])
    subgroup = forms.IntegerField(label='Подгруппа (0 — общая)', min_value=0, max_value=9)
    subject = forms.CharField(label='Предмет', required=False)
    teacher = forms.CharField(label='Преподаватель', required=False)
    classroom = forms.CharField(label='Кабинет', required=False)
    annotation = forms.CharField(label='Примечание', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    reviewed = forms.BooleanField(label='Строка проверена', required=False)
    remove = forms.BooleanField(label='Удалить занятие из этой выгрузки', required=False)
    reason = forms.CharField(label='Причина изменения', widget=forms.Textarea(attrs={'rows': 2}))

    def __init__(self, *args, groups, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'].choices = [(g, g) for g in groups]


class UploadRevisionForm(forms.Form):
    request_id = forms.UUIDField(widget=forms.HiddenInput)
    file = forms.FileField(label='Полная выгрузка JSON', help_text='Формат скачанной версии: groups, lessons, review_items.')
    reason = forms.CharField(label='Причина замены', widget=forms.Textarea(attrs={'rows': 2}))

    def clean_file(self):
        upload = self.cleaned_data['file']
        if upload.size > 20 * 1024 * 1024:
            raise forms.ValidationError('Максимальный размер — 20 МБ.')
        try:
            payload = json.loads(upload.read().decode('utf-8-sig'))
        except (ValueError, UnicodeError):
            raise forms.ValidationError('Ожидается JSON в кодировке UTF-8.')
        if not isinstance(payload, dict) or set(payload) != {'groups', 'lessons', 'review_items'}:
            raise forms.ValidationError('Нужна полная выгрузка с groups, lessons и review_items.')
        if (not isinstance(payload['groups'], list) or any(not isinstance(g, str) or not g.strip() for g in payload['groups'])
                or len(set(payload['groups'])) != len(payload['groups'])):
            raise forms.ValidationError('Список групп содержит некорректные значения.')
        for key in ('lessons', 'review_items'):
            if not isinstance(payload[key], list) or any(not isinstance(row, dict) for row in payload[key]):
                raise forms.ValidationError('Занятия и очередь ревью должны быть списками объектов.')
        return payload


class PublicationRangeForm(forms.Form):
    start_day_offset = forms.IntegerField(label='Начало: сдвиг от сегодняшней даты', initial=0)
    end_day_offset = forms.IntegerField(label='Конец: сдвиг от сегодняшней даты', required=False,
                                      help_text='Пустое значение — без верхней границы. Обе границы включаются.')
