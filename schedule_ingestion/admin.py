import json
import uuid
from copy import deepcopy

from django.contrib import admin, messages
from django.conf import settings
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html
from kombu.exceptions import OperationalError

from .models import (ExportRevision, Publication, PublicationDelivery, DeliveryResolution,
                     ScheduleSource, ParseRun, ParseAttempt, RunSheet)
from .admin_forms import SourceForm, LessonReviewForm, UploadRevisionForm, PublicationRangeForm
from .run_storage import load_export, save_export, StaleRevision
from .admin_display import (HistoryPresentation, PublicationPresentation, DeliveryPresentation,
                            instant, pretty, record_link, STATUS)

if getattr(settings, 'TABLEPARSER_LOCAL_SANDBOX', False):
    delivery_label = 'рассылки отключены' if getattr(settings, 'TABLEPARSER_DISABLE_DELIVERY', True) else 'реальная рассылка включена'
    admin.site.site_header = 'Локальный стенд TableParser · копия БД · ' + delivery_label


class IngestionHistoryAdmin(HistoryPresentation, admin.ModelAdmin):
    """Read-only history; publication/edit actions will use dedicated services."""
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return list(dict.fromkeys([field.name for field in self.model._meta.fields] + list(self.readonly_fields)))


@admin.register(ScheduleSource)
class ScheduleSourceAdmin(admin.ModelAdmin):
    form = SourceForm
    change_form_template = 'admin/schedule_ingestion/source_form.html'
    list_display = ['id', 'name', 'spreadsheet_id', 'enabled']
    list_display_links = ['id', 'name']
    readonly_fields = ['id']
    list_filter = ['enabled']
    search_fields = ['name', 'spreadsheet_id']
    actions = ['load_sources']

    @admin.action(description='Загрузить листы и разобрать расписание', permissions=['change'])
    def load_sources(self, request, queryset):
        from .tasks import runtime_options, source_parse_chain
        try:
            runtime_options()
        except ValueError:
            self.message_user(request, 'Ресурсы парсера не настроены.', level=messages.ERROR)
            return
        for source in queryset.order_by('pk'):
            if not source.enabled:
                self.message_user(request, f'Источник «{source}» выключен; запуск пропущен.', level=messages.WARNING)
                continue
            try:
                result = source_parse_chain(source.pk).apply_async()
            except OperationalError:
                self.message_user(request, f'Не удалось подтвердить постановку «{source}» в очередь. Проверьте worker перед повтором.', level=messages.ERROR)
                continue
            url = reverse('admin:schedule_ingestion_parserun_changelist') + f'?source__id__exact={source.pk}'
            self.message_user(request, format_html(
                'Источник «{}» поставлен в очередь ({}). <a href="{}">Открыть запуски</a>. '
                'Обновите список после обработки. Синхронизация выполняется отдельно из выгрузки.',
                source, result.id, url))


class HistoryInline(admin.TabularInline):
    extra = 0
    can_delete = False
    def has_add_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False


class AttemptInline(HistoryInline):
    model = ParseAttempt
    verbose_name_plural = 'Попытки разбора'
    fields = readonly_fields = ['attempt_status', 'started_at', 'finished_at', 'error_type']
    ordering = ['-started_at']

    @admin.display(description='Состояние')
    def attempt_status(self, obj):
        return STATUS.get(obj.status, obj.status)


class SheetInline(HistoryInline):
    model = RunSheet
    verbose_name_plural = 'Загруженные листы'
    fields = readonly_fields = ['name', 'position', 'content_id']


class ExportInline(HistoryInline):
    model = ExportRevision
    verbose_name_plural = 'Версии выгрузки'
    ordering = ['-number']
    fields = readonly_fields = ['number', 'created_at', 'author', 'reason', 'open_revision']

    @admin.display(description='Выгрузка')
    def open_revision(self, obj):
        return format_html('<a href="{}">Просмотреть</a>', reverse('admin:ingestion_review', args=[obj.pk]))


@admin.register(ParseRun)
class ParseRunAdmin(IngestionHistoryAdmin):
    list_display = ['run_label', 'source', 'captured_at', 'head_revision', 'latest_export']
    ordering = ['-captured_at', '-created_at']
    list_select_related = ['source']
    search_fields = ['source__name']
    readonly_fields = ['run_label', 'latest_export', 'configuration_json', 'manifest_json']
    fieldsets = [
        ('Запуск', {'fields': ['source', 'captured_at', 'head_revision', 'latest_export'],
                    'description': 'Время получения исходных листов и созданные из них версии выгрузки.'}),
        ('Воспроизведение и диагностика', {'classes': ['collapse'],
            'description': 'Created at — регистрация запуска. Reference date — опорная дата определения года. '
                           'Knowledge as of — срез знаний, доступных парсеру. Настройки и манифест фиксируют условия разбора.',
            'fields': ['created_at', 'reference_date', 'knowledge_as_of', 'configuration_json', 'manifest_json', 'id', 'acquisition_id']})]
    list_filter = ['source']
    date_hierarchy = 'captured_at'
    inlines = [SheetInline, AttemptInline, ExportInline]

    @admin.display(description='Запуск', ordering='captured_at')
    def run_label(self, obj):
        return instant(obj.captured_at)

    @admin.display(description='Последняя выгрузка')
    def latest_export(self, obj):
        revision = obj.exports.order_by('-number').first()
        return format_html('<a href="{}">Открыть v{}</a>', reverse('admin:ingestion_review', args=[revision.pk]), revision.number) if revision else 'Пока нет выгрузки'

    @admin.display(description='Настройки источника на момент загрузки')
    def configuration_json(self, obj):
        return pretty(obj.source_configuration)

    @admin.display(description='Версия парсера и ресурсов')
    def manifest_json(self, obj):
        return pretty(obj.parser_manifest)


@admin.register(ExportRevision)
class ExportRevisionAdmin(IngestionHistoryAdmin):
    list_display = ['number', 'source_label', 'run_link', 'created_at', 'author', 'review_link']
    ordering = ['-run__captured_at', '-run_id', '-number']
    list_select_related = ['run__source']
    list_filter = ['run__source']
    readonly_fields = ['source_label', 'run_link', 'review_link']
    fieldsets = [
        ('Выгрузка', {'fields': ['source_label', 'run_link', 'number', 'created_at', 'author', 'review_link']}),
        ('Комментарий к сохранению', {'fields': ['reason'], 'description': 'Причина создания всей версии. В старом редакторе — введённый комментарий к правке занятия; в общем редакторе — «Ревью выгрузки».'}),
        ('Технические сведения', {'classes': ['collapse'], 'fields': ['id', 'request_id', 'sha256'],
                                'description': 'Request ID защищает от повторного сохранения одного запроса. SHA256 проверяет целостность выгрузки.'})]
    search_fields = ['author', 'reason']
    exclude = ['payload']

    @admin.display(description='Источник', ordering='run__source__name')
    def source_label(self, obj):
        return obj.run.source.name

    @admin.display(description='Запуск', ordering='run__captured_at')
    def run_link(self, obj):
        return record_link('parserun', obj.run_id, instant(obj.run.captured_at))

    def get_readonly_fields(self, request, obj=None):
        return [f for f in super().get_readonly_fields(request, obj) if f != 'payload'] + ['review_link']

    @admin.display(description='Ревью')
    def review_link(self, obj):
        return format_html('<a href="{}">Занятия и публикация</a>', reverse('admin:ingestion_review', args=[obj.pk]))

    def get_urls(self):
        wrap = self.admin_site.admin_view
        return [
            path('<uuid:revision_id>/review/', wrap(self.review), name='ingestion_review'),
            path('<uuid:revision_id>/cell/<int:index>/', wrap(self.cell), name='ingestion_cell'),
            path('<uuid:revision_id>/batch/', wrap(self.batch), name='ingestion_batch'),
            path('<uuid:revision_id>/lesson/<int:index>/', wrap(self.edit), name='ingestion_edit'),
            path('<uuid:revision_id>/add/', wrap(self.edit), name='ingestion_add'),
            path('<uuid:revision_id>/upload/', wrap(self.upload), name='ingestion_upload'),
            path('<uuid:revision_id>/download/', wrap(self.download), name='ingestion_download'),
            path('<uuid:revision_id>/publish/', wrap(self.publish), name='ingestion_publish'),
        ] + super().get_urls()

    def revision(self, request, revision_id, permission=None):
        obj = get_object_or_404(ExportRevision.objects.select_related('run'), pk=revision_id)
        if not self.has_view_permission(request, obj) or (
                permission and not request.user.has_perm('schedule_ingestion.' + permission)):
            raise PermissionDenied
        return obj

    def render(self, request, obj, template, **context):
        return TemplateResponse(request, 'admin/schedule_ingestion/' + template, dict(
            self.admin_site.each_context(request), opts=self.model._meta, original=obj,
            revision=obj, title=f'Выгрузка № {obj.number}',
            delivery_disabled=getattr(settings, 'TABLEPARSER_DISABLE_DELIVERY', False), **context))

    def review_payload(self, obj):
        from .inline_review import restore_review_origin
        payload = load_export(obj.pk)
        first = obj.run.exports.order_by('number').first()
        if first and first.pk != obj.pk:
            restore_review_origin(payload, load_export(first.pk))
        return payload

    def review(self, request, revision_id):
        from .inline_review import review_state
        obj = self.revision(request, revision_id)
        payload = self.review_payload(obj)
        rows = list(enumerate(payload['lessons']))
        needs_review = sum(row.get('review_status') == 'needs_review' for _, row in rows)
        only_review = request.GET.get('needs_review') == '1'
        return self.render(request, obj, 'review.html',
            payload=payload,
            state=review_state(payload),
            needs_review=needs_review, only_review=only_review,
            can_review=request.user.has_perm('schedule_ingestion.review_export'),
            can_publish=request.user.has_perm('schedule_ingestion.publish_export'),
            publications=Publication.objects.filter(revision=obj).order_by('-requested_at'))

    def batch(self, request, revision_id):
        from .inline_review import replace_batch, review_state
        obj = self.revision(request, revision_id, 'review_export')
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)
        try:
            data = json.loads(request.body)
            payload = replace_batch(self.review_payload(obj), data)
            from .publication import prepare_payload
            prepare_payload(payload)
            saved = save_export(run_id=obj.run_id, expected_revision=obj.number,
                request_id=data['request_id'], author=request.user.get_username(), reason=data['reason'], **payload)
        except StaleRevision:
            latest = obj.run.exports.order_by('-number').first()
            return JsonResponse({'error': 'Выгрузка уже изменена в другом окне. Ваш черновик сохранён в этой вкладке.',
                'latest_url': reverse('admin:ingestion_review', args=[latest.pk])}, status=409)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            return JsonResponse({'error': str(error)}, status=400)
        return JsonResponse({'state': review_state(payload), 'number': saved.number,
            'url': reverse('admin:ingestion_review', args=[saved.pk])})

    def cell(self, request, revision_id, index):
        from .inline_review import cell_indices, replace_cell
        obj = self.revision(request, revision_id, 'review_export')
        payload = load_export(obj.pk)
        if index >= len(payload['lessons']):
            raise Http404
        indices = cell_indices(payload['lessons'], index)
        if request.method == 'GET':
            return JsonResponse({'indices': indices, 'rows': [payload['lessons'][i] for i in indices]})
        if request.method != 'POST':
            return JsonResponse({'error': 'Method not allowed'}, status=405)
        try:
            data = json.loads(request.body)
            payload = replace_cell(payload, indices, data)
            from .publication import prepare_payload
            prepare_payload(payload)
            saved = save_export(run_id=obj.run_id, expected_revision=obj.number,
                request_id=data['request_id'], author=request.user.get_username(),
                reason=data['reason'], **payload)
        except StaleRevision:
            latest = obj.run.exports.order_by('-number').first()
            return JsonResponse({'error': 'Другой пользователь уже сохранил новую версию. Ваши правки остались в редакторе.',
                'latest_url': reverse('admin:ingestion_review', args=[latest.pk])}, status=409)
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            return JsonResponse({'error': str(error)}, status=400)
        return JsonResponse({'payload': payload, 'number': saved.number,
            'url': reverse('admin:ingestion_review', args=[saved.pk])})

    def save(self, request, obj, form, payload):
        from .publication import prepare_payload
        try:
            prepare_payload(payload)  # Validate schedule fields before saving a complete version.
            saved = save_export(run_id=obj.run_id, expected_revision=obj.number,
                request_id=form.cleaned_data['request_id'], author=request.user.get_username(),
                reason=form.cleaned_data['reason'], **payload)
        except StaleRevision:
            form.add_error(None, 'Уже сохранена новая версия. Ваши правки оставлены в форме; откройте актуальную версию и перенесите их.')
        except (ValueError, TypeError, KeyError) as error:
            form.add_error(None, f'Выгрузка не сохранена: {error}')
        else:
            messages.success(request, 'Создана полная версия выгрузки. Для обновления расписания опубликуйте её отдельно.')
            return redirect('admin:ingestion_review', revision_id=saved.pk)

    def edit(self, request, revision_id, index=None):
        obj = self.revision(request, revision_id, 'review_export')
        payload = load_export(obj.pk)
        if index is not None and index >= len(payload['lessons']):
            raise Http404
        row = payload['lessons'][index] if index is not None else {}
        from schedule_csv import annotation_text
        annotation = annotation_text(row['annotations']) if 'annotations' in row else row.get('annotation', '')
        initial = dict(row, request_id=uuid.uuid4(), annotation=annotation, part=row.get('part') or 0,
                       subgroup=row.get('subgroup') or 0, reviewed=row.get('review_status') == 'reviewed')
        form = LessonReviewForm(request.POST or None, initial=initial, groups=payload['groups'])
        if request.method == 'POST' and form.is_valid():
            data = form.cleaned_data
            edited = deepcopy(row)
            for key in ('group', 'lesson_number', 'part', 'subgroup', 'subject', 'teacher', 'classroom'):
                edited[key] = data[key]
            edited.update(date=data['date'].isoformat(), review_status='reviewed' if data['reviewed'] else 'needs_review')
            if data['annotation'] != (annotation or ''):
                edited.pop('annotations', None)
                edited['annotation'] = data['annotation']
            if index is None:
                if data['remove']:
                    form.add_error('remove', 'Нельзя удалить ещё не добавленное занятие.')
                else:
                    payload['lessons'].append(edited)
            elif data['remove']:
                del payload['lessons'][index]
            else:
                payload['lessons'][index] = edited
            if not form.errors:
                response = self.save(request, obj, form, payload)
                if response:
                    return response
        latest = obj.run.exports.order_by('-number').first()
        return self.render(request, obj, 'edit.html', form=form, row=row, latest=latest, upload=False)

    def upload(self, request, revision_id):
        obj = self.revision(request, revision_id, 'review_export')
        form = UploadRevisionForm(request.POST or None, request.FILES or None, initial={'request_id': uuid.uuid4()})
        if request.method == 'POST' and form.is_valid():
            response = self.save(request, obj, form, form.cleaned_data['file'])
            if response:
                return response
        return self.render(request, obj, 'edit.html', form=form, upload=True,
                           latest=obj.run.exports.order_by('-number').first())

    def download(self, request, revision_id):
        obj = self.revision(request, revision_id)
        response = HttpResponse(json.dumps(load_export(obj.pk), ensure_ascii=False, indent=2), content_type='application/json')
        response['Content-Disposition'] = f'attachment; filename="export-{obj.pk}.json"'
        return response

    def publish(self, request, revision_id):
        obj = self.revision(request, revision_id, 'publish_export')
        from .publication import prepare_publication, prepare_payload
        from .tasks import resume_publication_chain
        from scheduler.dtos.lesson_sync_range import LessonSyncRange
        payload = load_export(obj.pk)
        form = PublicationRangeForm(request.POST or None)
        preview = None
        token = request.POST.get('confirmation', '')
        if request.method == 'POST' and token:
            try:
                preview = signing.loads(token, salt='ingestion-publication', max_age=3600)
                if preview['revision'] != str(obj.pk) or preview['user'] != str(request.user.pk):
                    raise signing.BadSignature
            except (signing.BadSignature, KeyError, TypeError):
                form.add_error(None, 'Подтверждение недействительно или устарело. Задайте период заново.')
                preview, token = None, ''
            else:
                try:
                    publication = prepare_publication(obj.pk, request_id=preview['request'],
                        requested_by=request.user.get_username(), resolved_range=preview['bounds'])
                    resume_publication_chain(publication.pk).apply_async()
                except (ValueError, KeyError, TypeError) as error:
                    form.add_error(None, f'Публикация не подготовлена: {error}')
                except (OperationalError, OSError):
                    form.add_error(None, 'Публикация сохранена, но очередь недоступна. Повторите подтверждение: будет использована та же публикация.')
                else:
                    messages.success(request, f'Публикация {publication.pk} поставлена в очередь.')
                    return redirect('admin:ingestion_review', revision_id=obj.pk)
        elif request.method == 'POST' and form.is_valid():
            try:
                prepare_payload(payload)
                bounds = LessonSyncRange.from_offsets(**form.cleaned_data)
            except (ValueError, KeyError, TypeError) as error:
                form.add_error(None, f'Проверьте выгрузку и период: {error}')
            else:
                preview = dict(revision=str(obj.pk), user=str(request.user.pk), request=str(uuid.uuid4()), bounds=bounds.to_dict())
                token = signing.dumps(preview, salt='ingestion-publication')
        display_bounds = LessonSyncRange.from_dict(preview['bounds']) if preview else None
        return self.render(request, obj, 'publish.html', form=form, preview=preview, confirmation=token,
            display_bounds=display_bounds,
            payload=payload, needs_review=sum(row.get('review_status') == 'needs_review' for row in payload['lessons']))


class DeliveryInline(DeliveryPresentation, HistoryInline):
    model = PublicationDelivery
    verbose_name_plural = 'Рассылка и отчёт'
    fields = readonly_fields = ['phase_label', 'delivery_status', 'finished_at', 'delivery_result', 'open_delivery']

    @admin.display(description='Состояние')
    def delivery_status(self, obj):
        return STATUS.get(obj.status, obj.status)

    @admin.display(description='Подробности')
    def open_delivery(self, obj):
        return record_link('publicationdelivery', obj.pk, 'Открыть')


@admin.register(Publication)
class PublicationAdmin(PublicationPresentation, IngestionHistoryAdmin):
    list_display = ['publication_label', 'source_label', 'export_link', 'period_label', 'state_label', 'requested_by', 'changes_label']
    list_select_related = ['revision__run__source']
    list_filter = ['status', 'revision__run__source', 'automatic']
    search_fields = ['revision__run__source__name', 'requested_by']
    ordering = ['-requested_at']
    date_hierarchy = 'requested_at'
    readonly_fields = ['source_label', 'export_link', 'period_label', 'state_label', 'changes_label', 'group_labels', 'summary_json', 'prepared_json']
    inlines = [DeliveryInline]
    fieldsets = [
        ('Публикация расписания', {'fields': ['source_label', 'export_link', 'state_label', 'period_label', 'group_labels'],
                                 'description': 'Применение конкретной версии выгрузки к расписанию за выбранный период.'}),
        ('Результат', {'fields': ['changes_label', 'requested_by', 'requested_at', 'applied_at', 'automatic']}),
        ('Подробный результат синхронизации', {'classes': ['collapse'], 'fields': ['summary_json']}),
        ('Технические сведения', {'classes': ['collapse'], 'fields': ['id', 'prepared_sha256', 'prepared_json']})]

    @admin.display(description='Публикация', ordering='requested_at')
    def publication_label(self, obj):
        return instant(obj.requested_at)


@admin.register(PublicationDelivery)
class PublicationDeliveryAdmin(DeliveryPresentation, IngestionHistoryAdmin):
    list_display = ['phase_label', 'publication_link', 'state_label', 'started_at', 'finished_at', 'error_type']
    list_select_related = ['publication__revision__run__source']
    list_filter = ['status', 'phase', 'publication__revision__run__source']
    search_fields = ['publication__revision__run__source__name', 'error_type']
    ordering = ['-publication__requested_at', '-pk']
    readonly_fields = ['phase_label', 'publication_link', 'state_label', 'delivery_result', 'result_json', 'resolution_links']
    fieldsets = [
        ('Доставка', {'fields': ['phase_label', 'publication_link', 'state_label', 'delivery_result'],
                     'description': 'Отдельный этап после синхронизации расписания: уведомления или административный отчёт.'}),
        ('Выполнение', {'fields': ['started_at', 'finished_at', 'error_type', 'resolution_links']}),
        ('Результат задачи', {'classes': ['collapse'], 'fields': ['result_json']}),
        ('Технические сведения', {'classes': ['collapse'], 'fields': ['id', 'token']})]

    @admin.display(description='Ручные решения')
    def resolution_links(self, obj):
        from django.utils.html import format_html_join
        return format_html_join(' · ', '<a href="{}">{}</a>', (
            (reverse('admin:schedule_ingestion_deliveryresolution_change', args=[r.pk]), str(r))
            for r in obj.resolutions.order_by('-created_at'))) or 'Ручных решений не было'


@admin.register(DeliveryResolution)
class DeliveryResolutionAdmin(IngestionHistoryAdmin):
    list_display = ['resolved_at', 'decision_label', 'delivery_link', 'actor', 'reason']
    list_select_related = ['delivery__publication__revision__run__source']
    list_filter = ['decision']
    search_fields = ['actor', 'reason', 'delivery__publication__revision__run__source__name']
    ordering = ['-created_at']
    readonly_fields = ['decision_label', 'delivery_link', 'previous_json']
    fieldsets = [
        ('Ручное решение по доставке', {'fields': ['decision_label', 'delivery_link', 'actor', 'created_at', 'reason'],
                                     'description': 'Журнал решений после неопределённого результата отправки. Обычные успешные рассылки записей здесь не создают.'}),
        ('Диагностика', {'classes': ['collapse'], 'fields': ['worker_stopped', 'previous_json', 'id']})]

    @admin.display(description='Когда', ordering='created_at')
    def resolved_at(self, obj):
        return instant(obj.created_at)

    @admin.display(description='Решение', ordering='decision')
    def decision_label(self, obj):
        return {'retry':'Повторить доставку', 'skip':'Пропустить доставку'}.get(obj.decision, obj.decision)

    @admin.display(description='Доставка')
    def delivery_link(self, obj):
        return record_link('publicationdelivery', obj.delivery_id, str(obj.delivery))

    @admin.display(description='Состояние до решения')
    def previous_json(self, obj):
        return pretty(obj.previous)
