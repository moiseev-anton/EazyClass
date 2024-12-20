from scheduler.activities.period_activities import fill_default_period_template


def make_active(modeladmin, request, queryset):
    queryset.update(is_active=True)


make_active.short_description = "Сделать активными выбранные записи"


def make_inactive(modeladmin, request, queryset):
    queryset.update(is_active=False)


make_inactive.short_description = "Сделать НЕ активными выбранные записи"


def toggle_active(modeladmin, request, queryset):
    for obj in queryset:
        obj.is_active = not obj.is_active
        obj.save()


toggle_active.short_description = "Переключить активность выбранных записей"


def reset_timetable(modeladmin, request, queryset):
    fill_default_period_template()
    modeladmin.message_user(request, "Шаблон звонков сброшен к стандартному виду.")


reset_timetable.short_description = "Сбросить шаблон звонков к стандартному виду"
