from django.contrib import admin
from .models import *
from .activities import *


@admin.register(Faculty)
class FacultyAdmin(admin.ModelAdmin):
    list_display = ('title', 'short_title', 'is_active', 'updated_at')
    search_fields = ('title', 'short_title')
    list_filter = ('is_active',)
    ordering = ('title',)
    actions = [make_active, make_inactive, toggle_active]


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ('title', 'faculty', 'grade', 'is_active', 'updated_at')
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


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('group', 'date', 'lesson_number', 'subject', 'teacher', 'classroom', 'is_active', 'updated_at')
    search_fields = ('group__title', 'subject__title', 'teacher__full_name', 'classroom__title')
    list_filter = ('group', 'subject', 'teacher', 'classroom', 'is_active', 'date')
    ordering = ('date', 'lesson_number')
    actions = [make_active, make_inactive, toggle_active]


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        'user_name', 'first_name', 'last_name', 'telegram_id', 'phone_number', 'subgroup', 'group', 'is_active',
        'registration_date')
    search_fields = ('user_name', 'first_name', 'last_name', 'telegram_id')
    list_filter = ('is_active', 'group', 'subgroup')
    ordering = ('user_name',)
    actions = [make_active, make_inactive, toggle_active]


@admin.register(LessonTimeTemplate)
class LessonTimeTemplateAdmin(admin.ModelAdmin):
    list_display = ('day_of_week', 'lesson_number', 'start_time', 'end_time')
    list_filter = ('day_of_week', 'lesson_number')
    actions = [reset_timetable]

    # def fill_lesson_times(self, request, queryset):
    #     fill_lesson_times.delay()  # Вызов задачи через Celery
    #     self.message_user(request, "Заполнение расписания начато. Проверьте логи выполнения.")
    #
    # def apply_template_changes(self, request, queryset):
    #     start_date = timezone.now().date()
    #     apply_template_changes.delay(start_date)  # Вызов задачи через Celery
    #     self.message_user(request, f"Применение изменений шаблона начато. Проверьте логи выполнения.")


@admin.register(LessonTime)
class LessonTimeAdmin(admin.ModelAdmin):
    list_display = ('date', 'lesson_number', 'start_time', 'end_time')
    list_filter = ('date', 'lesson_number')
