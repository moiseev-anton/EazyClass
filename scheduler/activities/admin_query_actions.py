import logging

from django.db import transaction
from eazyclass.logging_context import get_context

from django.contrib import admin, messages
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.widgets import AutocompleteSelect
from django.shortcuts import redirect, render
from django.utils import timezone

from scheduler.activities import fill_default_period_template
from scheduler.forms import ReplaceLessonRelatedFieldsForm
from scheduler.models import Lesson


logger = logging.getLogger(__name__)


def log_admin_action(request, model, action, message, **fields):
    """Report committed changes only, retaining the HTTP context for the callback."""
    context = {**get_context(), "event": f"admin.{action}", "user_id": request.user.pk,
               "model": model.__name__, **fields}
    if "count" in fields:
        message += f"; обработано записей: {fields['count']}"
    if "changed_fields" in fields:
        message += f"; поля: {fields['changed_fields']}"
    transaction.on_commit(lambda: logger.info(message, extra=context))


@admin.action(description="Сделать активными выбранные записи")
def make_active(modeladmin, request, queryset):
    count = queryset.update(is_active=True)
    log_admin_action(request, queryset.model, "activated", "Выполнена массовая активация записей", count=count)


@admin.action(description="Сделать НЕ активными выбранные записи")
def make_inactive(modeladmin, request, queryset):
    count = queryset.update(is_active=False)
    log_admin_action(request, queryset.model, "deactivated", "Выполнена массовая деактивация записей", count=count)


@admin.action(description="Переключить активность выбранных записей")
@transaction.atomic
def toggle_active(modeladmin, request, queryset):
    count = 0
    for obj in queryset:
        obj.is_active = not obj.is_active
        obj.save()
        count += 1
    log_admin_action(request, queryset.model, "activity_toggled", "Переключена активность записей", count=count)


@admin.action(description="Сбросить шаблон звонков к стандартному виду")
def reset_timetable(modeladmin, request, queryset):
    fill_default_period_template()
    log_admin_action(request, queryset.model, "timetable_reset", "Шаблон звонков сброшен к стандартному виду")
    modeladmin.message_user(request, "Шаблон звонков сброшен к стандартному виду.")


@admin.action(description="Заменить поля для выбранных записей")
def replace_lesson_related_fields(modeladmin, request, queryset):
    form = ReplaceLessonRelatedFieldsForm(request.POST or None)

    for field_name in ("teacher", "classroom", "subject", "group", "period", "annotation"):
        db_field = Lesson._meta.get_field(field_name)

        widget = AutocompleteSelect(
            db_field,
            modeladmin.admin_site,
        )

        form.fields[field_name].widget = widget
        form.fields[field_name].widget.choices = form.fields[field_name].choices

    if "apply" in request.POST and form.is_valid():
        update_data = form.cleaned_data["update_data"]

        updated_count = queryset.update(**update_data, updated_at=timezone.now())
        changed_fields = ", ".join(update_data.keys())
        log_admin_action(request, queryset.model, "lessons_updated", "Выполнена массовая замена полей занятий",
                         count=updated_count, changed_fields=changed_fields)

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
