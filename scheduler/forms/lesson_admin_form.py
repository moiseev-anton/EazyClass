from django import forms
from scheduler.models import Lesson, Period


class LessonAdminForm(forms.ModelForm):
    date = forms.DateField(
        label="Date",
        widget=forms.DateInput(attrs={"type": "date"}),
        required=True,
    )
    lesson_number = forms.IntegerField(
        label="Lesson #",
        min_value=0,
        max_value=9,
        required=True,
    )

    class Meta:
        model = Lesson
        fields = "__all__"
        exclude = ("period",)

    def __init__(self, *args, **kwargs):
        # Если редактируем существующий Lesson, предзаполняем дату и номер урока
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.period_id:
            self.fields["date"].initial = self.instance.period.date.strftime("%Y-%m-%d")
            self.fields["lesson_number"].initial = self.instance.period.lesson_number

    def save(self, commit=True):
        lesson = super().save(commit=False)

        date = self.cleaned_data["date"]
        lesson_number = self.cleaned_data["lesson_number"]

        period, _ = Period.objects.get_or_create(
            date=date,
            lesson_number=lesson_number
        )

        lesson.period = period

        if commit:
            lesson.save()
            self.save_m2m()

        return lesson
