from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from rangefilter.filters import DateRangeFilter

from scheduler.activities.admin_query_actions import make_active, make_inactive, toggle_active
from scheduler.forms import TimingForm, TimingInlineFormSet, PeriodTemplateForm
from scheduler.models import (
    Faculty,
    Group,
    Teacher,
    Subject,
    Classroom,
    # LessonBuffer,
    Lesson,
    User,
    Timing,
    # Subscription,
    PeriodTemplate,
    Period
)


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


# @admin.register(LessonBuffer)
# class LessonBufferAdmin(admin.ModelAdmin):
#     list_display = ('group', 'period', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
#     search_fields = ('group__title', 'subject__title', 'teacher__full_name', 'classroom__title')
#     list_filter = ('group', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
#     actions = [make_active, make_inactive, toggle_active]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('group', 'period', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
    search_fields = ('group__title', 'subject__title', 'teacher__full_name', 'classroom__title')
    list_filter = ('group', 'subject', 'teacher', 'classroom', 'subgroup', 'is_active')
    actions = [make_active, make_inactive, toggle_active]


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        'username', 'first_name', 'last_name', 'is_active', 'created_at')
    list_filter = ('is_active', )
    search_fields = ('username', 'first_name', 'last_name')
    readonly_fields = ('created_at',)

    fieldsets = (
        (None, {
            'fields': ('username', 'first_name', 'last_name', 'is_active', 'created_at')
        }),
        ('Permissions', {
            'fields': ('groups', 'user_permissions', 'is_staff', 'is_superuser'),
        }),

    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'telegram_id', 'phone_number', 'password1', 'password2',
                       'is_active'),
        }),
    )


class TimingInline(admin.TabularInline):
    """
    Inline для редактирования связанных таймингов в модели PeriodTemplate.

    - Использует кастомную форму TimingForm и формсет TimingInlineFormSet.
    - Подключает пользовательские JS и CSS для улучшения интерфейса.

    Attributes:
        model: Связанная модель Timing.
        form: Форма для редактирования таймингов.
        formset: Кастомный формсет с дополнительной валидацией.
        extra: Количество пустых строк для добавления нового тайминга.
        Media: Подключает пользовательские скрипты и стили.
    """
    model = Timing
    form = TimingForm
    formset = TimingInlineFormSet
    extra = 0  # Включаем один пустой тайминг

    class Media:
        js = ('scheduler/js/timing_weekdays_shadow.js',)
        css = {
            'all': ('scheduler/css/custom_timing_styles.css',),
        }


@admin.register(PeriodTemplate)
class PeriodTemplateAdmin(admin.ModelAdmin):
    """
    Административный интерфейс для модели PeriodTemplate.

    - Использует кастомную форму PeriodTemplateForm.
    - Отображает связанные тайминги через TimingInline.

    Attributes:
        form: Форма для редактирования PeriodTemplate.
        list_display: Поля, отображаемые в списке записей.
        search_fields: Поля для поиска.
        inlines: Inline для редактирования связанных объектов.
    """
    form = PeriodTemplateForm
    list_display = ('lesson_number', 'start_date', 'end_date')
    search_fields = ('lesson_number',)
    inlines = [TimingInline, ]


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('date', 'lesson_number', 'start_time', 'end_time')
    list_filter = ('date', ('date', DateRangeFilter), 'lesson_number')
