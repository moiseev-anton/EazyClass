from django import forms

from scheduler.models import PeriodTemplate


class PeriodTemplateForm(forms.ModelForm):
    """
    Форма для валидации и редактирования модели PeriodTemplate.

    Проверяет:
    - Дата окончания должна быть позже даты начала.
    - Периоды с одинаковым номером урока не должны пересекаться.
    """
    class Meta:
        model = PeriodTemplate
        fields = ['lesson_number', 'start_date', 'end_date']

    def clean(self) -> dict:
        """
        Выполняет валидацию формы.

        Проверяет:
        - Если дата окончания указана, она должна быть позже даты начала.
        - Периоды с одинаковым lesson_number не должны пересекаться.

        Returns:
            dict: Очищенные данные формы.

        Raises:
            forms.ValidationError: Если найдены пересечения периодов или дата окончания раньше начала.
        """
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
