from datetime import date

from django.contrib import messages
from django.shortcuts import render, redirect

from scheduler.forms import PeriodChangeFormSet
from scheduler.models import PeriodTemplate, Period


def apply_changes_view(request):
    if request.method == "POST":
        formset = PeriodChangeFormSet(request.POST)
        start_date = request.POST.get("start_date")
        end_date = request.POST.get("end_date")

        if formset.is_valid():
            for form in formset:
                lesson_data = form.cleaned_data
                lesson_number = lesson_data["lesson_number"]
                start_time = lesson_data["start_time"]
                end_time = lesson_data["end_time"]
                days_of_week = lesson_data["days_of_week"]

                # Обрабатываем изменения для каждого дня недели
                for day in days_of_week:
                    if end_date:  # Временные изменения
                        Period.objects.filter(
                            date__range=(start_date, end_date),
                            lesson_number=lesson_number,
                            date__week_day=int(day) + 1
                        ).update(
                            start_time=start_time,
                            end_time=end_time
                        )
                    else:  # Постоянные изменения
                        PeriodTemplate.objects.filter(
                            day_of_week=day, lesson_number=lesson_number
                        ).update(
                            start_time=start_time,
                            end_time=end_time
                        )
            messages.success(request, "Изменения успешно применены!")
            return redirect("admin:scheduler_period_template_changelist")

    else:
        formset = PeriodChangeFormSet()

    context = {
        "formset": formset,
        "start_date": date.today(),
    }
    return render(request, "admin/apply_template_changes.html", context)
