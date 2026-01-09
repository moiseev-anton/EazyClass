from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from rangefilter.filters import DateRangeFilter
from admin_auto_filters.filters import AutocompleteFilter

# Local imports
from scheduler.activities.admin_query_actions import make_active, make_inactive, toggle_active
from scheduler.forms import TimingForm, TimingInlineFormSet, PeriodTemplateForm
from scheduler.models import (
    Faculty,
    Group,
    SocialAccount,
    Teacher,
    Subject,
    Classroom,
    Lesson,
    User,
    Timing,
    Subscription,
    TeacherSubscription,
    GroupSubscription,
    PeriodTemplate,
    Period,
)
from polymorphic.admin import (
    PolymorphicParentModelAdmin,
    PolymorphicChildModelAdmin,
    PolymorphicChildModelFilter,
)



# ---------------------------------------------------------------------------
# Autocomplete filters
# ---------------------------------------------------------------------------

class GroupFilter(AutocompleteFilter):
    """Filter lessons by `group` using autocomplete."""
    title = 'Group'
    field_name = 'group'


class TeacherFilter(AutocompleteFilter):
    """Filter lessons by `teacher` using autocomplete."""
    title = 'Teacher'
    field_name = 'teacher'


class SubjectFilter(AutocompleteFilter):
    """Filter lessons by `subject` using autocomplete."""
    title = 'Subject'
    field_name = 'subject'


class FacultyFilter(AutocompleteFilter):
    """Filter groups by `faculty` using autocomplete."""
    title = 'Faculty'
    field_name = 'faculty'


class ClassroomFilter(AutocompleteFilter):
    """Filter groups by `faculty` using autocomplete."""
    title = 'Classroom'
    field_name = 'classroom'


# ---------------------------------------------------------------------------
# Helper BaseAdmin classes
# ---------------------------------------------------------------------------

class BaseActiveAdmin(admin.ModelAdmin):
    """Common admin settings for models with active/inactive actions."""
    actions = [make_active, make_inactive, toggle_active]
    list_per_page = 50


class SocialAccountInline(admin.TabularInline):
    """Inline для редактирования SocialAccount внутри UserAdmin."""
    model = SocialAccount
    extra = 0


# ---------------------------------------------------------------------------
# ModelAdmin classes
# ---------------------------------------------------------------------------


@admin.register(Faculty)
class FacultyAdmin(BaseActiveAdmin):
    list_display = ('short_title', 'title', 'is_active', 'updated_at', 'created_at', 'id')
    search_fields = ('title', 'short_title')
    readonly_fields = ('created_at', 'updated_at')
    list_filter = ('is_active',)
    list_display_links = ('short_title', 'title')
    ordering = ('title',)


@admin.register(Group)
class GroupAdmin(BaseActiveAdmin):
    list_display = ('title', 'grade', 'faculty', 'endpoint', 'is_active', 'updated_at', 'created_at', 'id')
    search_fields = ('title',)
    list_filter = (FacultyFilter, 'grade', 'is_active')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('faculty', 'grade',)
    autocomplete_fields = ('faculty',)
    

@admin.register(Teacher)
class TeacherAdmin(BaseActiveAdmin):
    list_display = ('short_name', 'full_name', 'endpoint', 'is_active')
    search_fields = ('full_name', 'short_name')
    list_filter = ('is_active',)
    ordering = ('full_name',)


@admin.register(Subject)
class SubjectAdmin(BaseActiveAdmin):
    list_display = ('id', 'title', 'is_active')
    search_fields = ('title',)
    list_filter = ('is_active',)
    ordering = ('title',)


@admin.register(Classroom)
class ClassroomAdmin(BaseActiveAdmin):
    list_display = ('title', 'is_active')
    search_fields = ('title',)
    list_filter = ('is_active',)
    ordering = ('title',)


@admin.register(Lesson)
class LessonAdmin(BaseActiveAdmin):
    list_display = ('id', 'period_date', 'period_lesson_number', 'group', 'teacher', 'classroom', 'subgroup', 'is_active', 'subject')
    search_fields = ('group__title', 'subject__title', 'teacher__full_name', 'classroom__title')
    list_filter = (
        GroupFilter,
        TeacherFilter,
        SubjectFilter,
        ClassroomFilter,
        ('period__date', DateRangeFilter),
        'period__lesson_number',
        'subgroup',
        'is_active',
    )
    list_select_related = ('period', 'group', 'teacher', 'classroom', 'subject')
    autocomplete_fields = ('group', 'teacher', 'classroom', 'subject', 'period')
    list_display_links = ('id', 'subject')
    ordering = ('-period__date', 'period__lesson_number', 'group',)
    readonly_fields = ('created_at', 'updated_at')

    def period_date(self, obj):
        return obj.period.date if obj.period_id else None
    period_date.admin_order_field = 'period__date'
    period_date.short_description = 'Date'

    def period_lesson_number(self, obj):
        return obj.period.lesson_number if obj.period_id else None
    period_lesson_number.admin_order_field = 'period__lesson_number'
    period_lesson_number.short_description = 'Lesson #'

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['period'].help_text = (
            'Поиск period по дате в формате YYYY-MM-DD'
        )
        return form

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    inlines = (SocialAccountInline,)
    list_display = ('id','username', 'first_name', 'last_name', 'notify_schedule_updates', 'notify_upcoming_lessons', 'updated_at', 'created_at', 'is_staff', 'is_active',)
    list_display_links = ('id', 'username')
    list_filter = ('is_active', )
    list_editable = ('notify_schedule_updates', 'notify_upcoming_lessons',)
    search_fields = ('username', 'first_name', 'last_name', 'id')
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        (None, {
            'fields': ('username', 'first_name', 'last_name', 'is_active')
        }),
        ('Notifications', {
            'fields': ('notify_schedule_updates', 'notify_upcoming_lessons')
        }),
        ('Permissions', {
            'fields': ('groups', 'user_permissions', 'is_staff', 'is_superuser'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    # Admins create users here (passwords are intended only for admin login).
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'first_name', 'last_name', 'password1', 'password2', 'is_staff', 'is_superuser', 'is_active'),
        }),
    )

@admin.register(SocialAccount)
class SocialAccountAdmin(admin.ModelAdmin):
    list_display = ('user', 'platform', 'social_id', 'is_blocked', 'extra_data')
    list_editable = ('is_blocked',)
    search_fields = ()
    list_select_related = ('user',)
    autocomplete_fields = ('user',)
    list_filter = ('platform', 'is_blocked')



class TimingInline(admin.TabularInline):
    """
    Inline для редактирования связанных таймингов в модели PeriodTemplate.

    - Использует кастомную форму TimingForm и формсет TimingInlineFormSet.
    - Подключает кастомные JS и CSS для улучшения интерфейса.

    Attributes:
        model: Связанная модель Timing.
        form: Форма для редактирования таймингов.
        formset: Кастомный формсет с дополнительной валидацией.
        extra: Количество пустых строк для добавления нового тайминга.
        Media: Подключает кастомные скрипты и стили.
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
    inlines = (TimingInline,)


@admin.register(Period)
class PeriodAdmin(admin.ModelAdmin):
    list_display = ('id', 'date', 'lesson_number', 'start_time', 'end_time')
    list_filter = (('date', DateRangeFilter), 'lesson_number')
    date_hierarchy = 'date'
    ordering = ('-date', 'lesson_number',)
    search_fields = ('date',)


# ---------------------------------------------------------------------------
# Polymorphic Subscription
# ---------------------------------------------------------------------------

class BaseSubscriptionChildAdmin(PolymorphicChildModelAdmin):
    base_model = Subscription
    readonly_fields = ('created_at', 'updated_at')
    def get_model_perms(self, request):
        """Hide child subscription models from the admin index/app list."""
        return {}


@admin.register(TeacherSubscription)
class TeacherSubscriptionAdmin(BaseSubscriptionChildAdmin):
    base_model = TeacherSubscription
    autocomplete_fields = ('user', 'teacher',)



@admin.register(GroupSubscription)
class GroupSubscriptionAdmin(BaseSubscriptionChildAdmin):
    base_model = GroupSubscription
    autocomplete_fields = ('user', 'group',)


@admin.register(Subscription)
class SubscriptionAdmin(PolymorphicParentModelAdmin):
    base_model = Subscription
    child_models = (TeacherSubscription, GroupSubscription)
    list_display = ('id', 'user', 'subscription_object', 'created_at', 'updated_at')
    list_filter = (PolymorphicChildModelFilter, 'created_at')
    list_select_related = ('user',)
    autocomplete_fields = ('user',)
    
    def subscription_object(self, obj):
        # Попытаться получить реальный (дочерний) экземпляр и вывести связанный объект
        real = obj
        try:
            real = obj.get_real_instance()
        except Exception:
            # Если методы polymorphic недоступны, используем исходный объект
            real = obj

        field = getattr(real, 'subscription_object_field', None)
        if field and hasattr(real, field):
            return getattr(real, field)

        # fallback — попробовать найти первое поле, отличное от 'user'
        for f in ('teacher', 'group'):
            if hasattr(real, f):
                return getattr(real, f)
        return None
    subscription_object.short_description = 'Object'

