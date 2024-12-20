from django.contrib import admin
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path
from rangefilter.filters import DateRangeFilter
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from scheduler.activities.admin_query_actions import *
from scheduler.activities.period_activities import apply_template_changes
from scheduler.models import *


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('title', 'short_title', 'is_active', 'updated_at')
    search_fields = ('title', 'short_title')
    list_filter = ('is_active',)
    ordering = ('title',)
    actions = [make_active, make_inactive, toggle_active]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'faculty', 'grade', 'is_active', 'updated_at')
    search_fields = ('title',)
    list_filter = ('faculty', 'grade', 'is_active')
    ordering = ('title',)
    actions = [make_active, make_inactive, toggle_active]


@admin.register(Teacher)
class TeacherAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'short_name', 'is_active')
    search_fields = ('full_name', 'short_name')
    list_filter = ('is_active',)
    ordering = ('full_name',)
    actions = [make_active, make_inactive, toggle_active]


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active')
    search_fields = ('title',)
    list_filter = ('is_active',)
    ordering = ('title',)
    actions = [make_active, make_inactive, toggle_active]


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_active')
    search_fields = ('title',)
    list_filter = ('is_active',)
    ordering = ('title',)
    actions = [make_active, make_inactive, toggle_active]


@admin.register(LessonBuffer)
class LessonBufferAdmin(admin.ModelAdmin):
    list_display = ('group', 'period', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
    search_fields = ('group__title', 'subject__title', 'teacher__full_name', 'classroom__title')
    list_filter = ('group', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
    actions = [make_active, make_inactive, toggle_active]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('group', 'period', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
    search_fields = ('group__title', 'subject__title', 'teacher__full_name', 'classroom__title')
    list_filter = ('group', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
    actions = [make_active, make_inactive, toggle_active]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'first_name', 'last_name', 'telegram_id', 'is_active', 'date_joined', 'subscription_info')
    list_filter = ('is_active', 'date_joined')
    search_fields = ('username', 'first_name', 'last_name', 'telegram_id')
    readonly_fields = ('date_joined', 'subscription_info')

    fieldsets = (
        (None, {
            'fields': ('username', 'first_name', 'last_name', 'telegram_id', 'phone_number', 'is_active', 'date_joined')
        }),
        ('Permissions', {
            'fields': ('groups', 'user_permissions', 'is_staff', 'is_superuser'),
        }),
        ('Notification Settings', {
            'fields': ('notify_on_schedule_change', 'notify_on_lesson_start'),
        }),
        ('Subscription', {
            'fields': ('subscription_info',),
        }),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'telegram_id', 'phone_number', 'password1', 'password2',
                       'is_active'),
        }),
    )

    def subscription_info(self, obj):
        # Этот метод должен быть обновлен для отображения всех подписок пользователя
        subscriptions = Subscription.objects.filter(user=obj)
        return ", ".join([f"{sub.content_object}" for sub in subscriptions]) if subscriptions else "No subscriptions"

    subscription_info.short_description = 'Subscription Info'


@admin.register(PeriodTemplate)
class PeriodTemplateAdmin(admin.ModelAdmin):
    list_display = ('day_of_week', 'lesson_number', 'start_time', 'end_time')
    list_filter = ('day_of_week', 'lesson_number')
    actions = [reset_timetable]
    change_list_template = "admin/scheduler/period_template/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('apply-template-changes/', self.admin_site.admin_view(self.apply_template_changes),
                 name='apply_template_changes')
        ]
        return custom_urls + urls

    def apply_template_changes(self, request):
        if request.method == 'POST':
            start_date = request.POST.get('start_date')
            if start_date:
                try:
                    apply_template_changes(start_date)
                    self.message_user(request, f'Changes applied successfully from {start_date}.')
                except ValueError as e:
                    self.message_user(request, str(e), level='error')
                return redirect('..')

        context = dict(
            self.admin_site.each_context(request),
            title="Применить шаблон звонков",
            opts=self.model._meta,
            action_checkbox_name=admin.helpers.ACTION_CHECKBOX_NAME,
        )
        return TemplateResponse(request, "admin/apply_template_changes.html", context)


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('date', 'lesson_number', 'start_time', 'end_time')
    list_filter = ('date', ('date', DateRangeFilter), 'lesson_number')
