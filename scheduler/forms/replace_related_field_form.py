# scheduler/forms.py

from django import forms
from scheduler.models import Teacher, Classroom, Subject, Group, Period


class ReplaceLessonRelatedFieldsForm(forms.Form):
    teacher = forms.ModelChoiceField(
        label="Новый преподаватель",
        queryset=Teacher.objects.all(),
        required=False,
    )
    classroom = forms.ModelChoiceField(
        label="Новый кабинет",
        queryset=Classroom.objects.all(),
        required=False,
    )
    subject = forms.ModelChoiceField(
        label="Новый предмет",
        queryset=Subject.objects.all(),
        required=False,
    )
    group = forms.ModelChoiceField(
        label="Новая группа",
        queryset=Group.objects.all(),
        required=False,
    )
    period = forms.ModelChoiceField(
        label="Новый период",
        queryset=Period.objects.all(),
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()

        update_data = {
            field: cleaned_data[field]
            for field in ("teacher", "classroom", "subject", "group", "period")
            if cleaned_data.get(field) is not None
        }

        if not update_data:
            raise forms.ValidationError(
                "Выберите хотя бы одно новое значение."
            )

        cleaned_data["update_data"] = update_data
        return cleaned_data