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
    part = Period._meta.get_field("part").formfield(label="Part")

    class Meta:
        model = Lesson
        fields = "__all__"
        exclude = ("period",)

    def __init__(self, *args, **kwargs):
        # При редактировании предзаполняем все поля, определяющие период.
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.period_id:
            self.fields["date"].initial = self.instance.period.date.strftime("%Y-%m-%d")
            self.fields["lesson_number"].initial = self.instance.period.lesson_number
            self.fields["part"].initial = self.instance.period.part

    def save(self, commit=True):
        lesson = super().save(commit=False)

        date = self.cleaned_data["date"]
        lesson_number = self.cleaned_data["lesson_number"]

        period, _ = Period.objects.get_or_create(
            date=date,
            lesson_number=lesson_number,
            part=self.cleaned_data["part"],
        )

        lesson.period = period

        if commit:
            lesson.save()
            self.save_m2m()

        return lesson
