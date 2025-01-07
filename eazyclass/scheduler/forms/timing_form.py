import logging

from django import forms
from django.db import transaction
from django.forms import BaseInlineFormSet

from scheduler.models import Timing, TimingWeekDay

logger = logging.getLogger(__name__)

DAYS_OF_WEEK = [
    (0, 'Пн'),
    (1, 'Вт'),
    (2, 'Ср'),
    (3, 'Чт'),
    (4, 'Пт'),
    (5, 'Сб'),
    (6, 'Вс'),
]


class TimingForm(forms.ModelForm):
    weekdays = forms.MultipleChoiceField(
        choices=DAYS_OF_WEEK,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'timing-weekdays'}),
        required=False,
        label="Дни недели"
    )

    class Meta:
        model = Timing
        fields = ['start_time', 'end_time', 'weekdays']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            # Предзаполнение выбранных дней недели
            self.fields['weekdays'].initial = list(
                self.instance.weekdays.values_list('day_of_week', flat=True)
            )

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')

        if start_time and end_time and start_time > end_time:
            raise forms.ValidationError("Время начала не может быть позже времени окончания.")

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        instance = super().save(commit=commit)
        self.synch_weekdays()
        return instance

    def synch_weekdays(self):
        timing = self.instance
        if not timing.pk:  # Если объект еще не сохранен
            logger.warning("Объект Timing еще не сохранен. Пропускаем синхронизацию.")
            return

        current_days = set(timing.weekdays.values_list('day_of_week', flat=True))
        new_days = set(self.cleaned_data.get('weekdays', []))

        # Удаляем дни недели, которых больше нет
        days_to_remove = current_days - new_days
        if days_to_remove:
            TimingWeekDay.objects.filter(
                timing=timing, day_of_week__in=days_to_remove
            ).delete()

        # Добавляем новые дни недели
        days_to_add = new_days - current_days
        if days_to_add:
            TimingWeekDay.objects.bulk_create([
                TimingWeekDay(timing=timing, day_of_week=day) for day in days_to_add
            ])


class TimingInlineFormSet(BaseInlineFormSet):
    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        affected_weekdays = set()
        for form in self.forms:
            if form.cleaned_data.get('DELETE', False):
                continue

            weekdays = set(form.cleaned_data.get('weekdays', []))

            if affected_weekdays & weekdays:
                raise forms.ValidationError(f"Пересечение таймингов по дням недели.")
            affected_weekdays |= weekdays

    @transaction.atomic
    def save(self, commit=True):
        instances = super().save(commit=True)  # Сохраняем тайминги

        if commit:
            for form in self.forms:
                if form.has_changed() and not form.cleaned_data.get('DELETE', False):
                    form.synch_weekdays()

        return instances
