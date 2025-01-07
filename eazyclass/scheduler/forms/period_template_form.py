from django import forms

from scheduler.models import PeriodTemplate


class PeriodTemplateForm(forms.ModelForm):
    class Meta:
        model = PeriodTemplate
        fields = ['lesson_number', 'start_date', 'end_date']

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        lesson_number = cleaned_data.get('lesson_number')
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if end_date and end_date < start_date:
            raise forms.ValidationError("Дата окончания должна быть позже начала")

        if PeriodTemplate.objects.overlapping(
                lesson_number=lesson_number,
                start_date=start_date,
                end_date=end_date,
                exclude_pk=self.instance.pk
        ).exists():
            raise forms.ValidationError("Период пересекается с другим шаблоном.")

        return cleaned_data
