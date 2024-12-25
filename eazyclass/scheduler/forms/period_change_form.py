from django import forms
from django.forms import formset_factory


class PeriodChangeForm(forms.Form):
    lesson_number = forms.IntegerField(label="Номер урока")
    start_time = forms.TimeField(label="Время начала", widget=forms.TimeInput(attrs={"type": "time"}))
    end_time = forms.TimeField(label="Время окончания", widget=forms.TimeInput(attrs={"type": "time"}))
    days_of_week = forms.MultipleChoiceField(
        label="Дни недели",
        choices=[
            (0, "Пн"),
            (1, "Вт"),
            (2, "Ср"),
            (3, "Чг"),
            (4, "Пт"),
            (5, "Сб"),
            (6, "Вс"),
        ],
        widget=forms.CheckboxSelectMultiple,
    )


PeriodChangeFormSet = formset_factory(PeriodChangeForm, extra=1)
