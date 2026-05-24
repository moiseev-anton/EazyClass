from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.widgets import AutocompleteSelect
from django.shortcuts import redirect, render

from scheduler.activities import fill_default_period_template
from scheduler.forms import ReplaceLessonRelatedFieldsForm
from scheduler.models import Lesson


@admin.action(description="Сделать активными выбранные записи")
def make_active(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description="Сделать НЕ активными выбранные записи")
def make_inactive(modeladmin, request, queryset):
    queryset.update(is_active=False)


@admin.action(description="Переключить активность выбранных записей")
def toggle_active(modeladmin, request, queryset):
    for obj in queryset:
        obj.is_active = not obj.is_active
        obj.save()


@admin.action(description="Сбросить шаблон звонков к стандартному виду")
def reset_timetable(modeladmin, request, queryset):
    fill_default_period_template()
    modeladmin.message_user(request, "Шаблон звонков сброшен к стандартному виду.")


@admin.action(description="Заменить поля для выбранных записей")
def replace_lesson_related_fields(modeladmin, request, queryset):
    form = ReplaceLessonRelatedFieldsForm(request.POST or None)

    for field_name in ("teacher", "classroom", "subject", "group", "period"):
        db_field = Lesson._meta.get_field(field_name)

        widget = AutocompleteSelect(
            db_field,
            modeladmin.admin_site,
        )

        form.fields[field_name].widget = widget
        form.fields[field_name].widget.choices = form.fields[field_name].choices

    if "apply" in request.POST and form.is_valid():
        update_data = form.cleaned_data["update_data"]

        updated_count = queryset.update(**update_data)
        changed_fields = ", ".join(update_data.keys())

        modeladmin.message_user(
            request,
            f"Изменено {updated_count} Lessons. Измененные поля: {changed_fields}",
            messages.SUCCESS,
        )
        return redirect(request.get_full_path())

    return render(
        request,
        "admin/replace_lesson_related_fields.html",
        {
            "title": "Замена полей для всех выбранных Lesson",
            "queryset": queryset,
            "form": form,
            "action_checkbox_name": ACTION_CHECKBOX_NAME,
        },
    )
