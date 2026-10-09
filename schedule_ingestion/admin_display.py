"""Read-only presentation of ingestion history, without changing stored records."""
import json

from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join


def instant(value):
    return timezone.localtime(value).strftime('%d.%m.%Y %H:%M') if value else '—'


def pretty(value):
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return format_html('<pre class="ingestion-json">{}</pre>', value)
    return format_html('<pre class="ingestion-json">{}</pre>', json.dumps(value, ensure_ascii=False, indent=2))


def record_link(model, pk, label):
    return format_html('<a href="{}">{}</a>', reverse('admin:schedule_ingestion_' + model + '_change', args=[pk]), label)


STATUS = {'pending':'Ожидает', 'applied':'Расписание обновлено', 'superseded':'Заменена более новой публикацией',
          'sending':'Выполняется', 'completed':'Завершено', 'uncertain':'Нужна проверка доставки',
          'skipped':'Пропущено', 'running':'Выполняется', 'succeeded':'Успешно', 'failed':'Ошибка', 'abandoned':'Прервано'}


class HistoryPresentation:
    class Media:
        css = {'all': ('schedule_ingestion/history.css',)}

    @admin.display(description='Состояние', ordering='status')
    def state_label(self, obj):
        tone = 'success' if obj.status in ('applied', 'completed', 'succeeded') else 'error' if obj.status in ('uncertain', 'failed') else 'neutral'
        return format_html('<span class="ingestion-status {}">{}</span>', tone, STATUS.get(obj.status, obj.status))

    def change_view(self, request, object_id, form_url='', extra_context=None):
        obj = self.get_object(request, object_id)
        context = dict(extra_context or {})
        if obj is not None:
            context.update(title=str(obj), subtitle=None)
        return super().change_view(request, object_id, form_url, context)


class PublicationPresentation:
    @admin.display(description='Источник', ordering='revision__run__source__name')
    def source_label(self, obj):
        return obj.revision.run.source.name

    @admin.display(description='Выгрузка')
    def export_link(self, obj):
        return format_html('<a href="{}">{} · v{}</a>', reverse('admin:ingestion_review', args=[obj.revision_id]), instant(obj.revision.run.captured_at), obj.revision.number)

    @admin.display(description='Период')
    def period_label(self, obj):
        return f'{obj.start_date:%d.%m.%Y} — ' + (f'{obj.end_date:%d.%m.%Y}' if obj.end_date else 'без ограничения')

    @admin.display(description='Изменения расписания')
    def changes_label(self, obj):
        if obj.status != 'applied':
            return 'Расписание ещё не изменено этой публикацией' if obj.status == 'pending' else 'Не применена: есть более новая публикация'
        def count(key):
            value = (obj.summary or {}).get(key, [])
            return len(value) if isinstance(value, (list, dict)) else value
        return format_html('<div class="ingestion-metrics">Добавлено <b>{}</b> · Обновлено <b>{}</b> · Удалено <b>{}</b></div>', count('added'), count('updated'), count('removed'))

    @admin.display(description='Группы')
    def group_labels(self, obj):
        from .run_storage import load_export
        return format_html('<div class="ingestion-chips">{}</div>', format_html_join('', '<span>{}</span>', ((g,) for g in load_export(obj.revision_id)['groups'])))

    @admin.display(description='Полный результат синхронизации')
    def summary_json(self, obj):
        return pretty(obj.summary)

    @admin.display(description='Подготовленные данные')
    def prepared_json(self, obj):
        return pretty(obj.prepared_payload)


class DeliveryPresentation:
    @admin.display(description='Этап', ordering='phase')
    def phase_label(self, obj):
        return {'notifications':'Рассылка уведомлений', 'report':'Административный отчёт'}.get(obj.phase, obj.phase)

    @admin.display(description='Публикация')
    def publication_link(self, obj):
        p = obj.publication
        return record_link('publication', p.pk, f'{p.revision.run.source.name} · {instant(p.requested_at)} · v{p.revision.number}')

    @admin.display(description='Результат')
    def delivery_result(self, obj):
        if (obj.result or {}).get('publication', {}).get('delivery_disabled'):
            return 'Пропущено: рассылки отключены на локальном стенде.'
        if obj.status == 'uncertain':
            return 'Результат отправки неизвестен. Перед повтором требуется ручная проверка, чтобы не отправить сообщения дважды.'
        notices = (obj.result or {}).get('notification_summary')
        if obj.phase == 'notifications' and obj.status == 'completed' and isinstance(notices, dict):
            return format_html('Успешно: <b>{}</b> · Ошибок: <b>{}</b> · Заблокировано: <b>{}</b>',
                               notices.get('success_count', '—'), notices.get('failed_count', '—'),
                               len(notices.get('blocked_chat_ids') or []))
        return {'pending':'Ожидает выполнения.', 'sending':'Задача выполняется.', 'completed':'Этап завершён. Подробный результат доступен ниже.', 'skipped':'Этап пропущен.'}.get(obj.status, obj.status)

    @admin.display(description='Полный результат задачи')
    def result_json(self, obj):
        return pretty(obj.result)
