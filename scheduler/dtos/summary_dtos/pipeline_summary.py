from typing import Any, Callable, Dict, List, Optional, Union
from html import escape

from scheduler.dtos.summary_dtos.base_summary_dto import BaseSummary, register_summary


@register_summary
class PipelineSummary(BaseSummary):
    """Сводный отчёт по этапам пайплайна (скрапинг/парсинг → синхронизация → уведомления)."""

    spider_result: Optional[dict] = None
    sync_summary: Optional[dict] = None
    notification_summary: Optional[Union[dict, BaseSummary]] = None
    publication: Optional[dict] = None

    def model_dump(self, **kwargs):
        """Автоматически сериализует вложенные summary-модели."""
        data = super().model_dump(**kwargs)

        if isinstance(self.notification_summary, BaseSummary):
            data["notification_summary"] = self.notification_summary.model_dump(**kwargs)

        return data

    @property
    def parts(self) -> dict[str, object]:
        parts: dict[str, object] = {}

        if self.spider_result:
            parts["spider"] = {
                "total_groups": self.spider_result.get("total_groups"),
                "skipped": self.spider_result.get("skipped"),
                "parsed": self.spider_result.get("parsed"),
                "no_change": self.spider_result.get("no_change"),
                "errors": self.spider_result.get("errors"),
                "error_groups": self.spider_result.get("error_groups", []),
                "total_lessons": self.spider_result.get("total_lessons"),
                "closing_reason": self.spider_result.get("closing_reason"),
            }

        if self.sync_summary:
            parts["sync"] = {
                "added": len(self.sync_summary.get("added", [])),
                "updated": len(self.sync_summary.get("updated", [])),
                "removed": len(self.sync_summary.get("removed", [])),
            }

        if isinstance(self.notification_summary, BaseSummary):
            parts["notifier"] = self.notification_summary.parts
        elif isinstance(self.notification_summary, dict):
            parts["notifier"] = {
                "success": self.notification_summary.get("success_count"),
                "failed": self.notification_summary.get("failed_count"),
                "blocked": len(self.notification_summary.get("blocked_chat_ids", [])),
            }

        return parts

    @classmethod
    def deserialize(cls, data: dict) -> "PipelineSummary":
        """Десериализация, включая вложенные summary."""
        notif_data = data.get("notification_summary")

        if isinstance(notif_data, dict) and "type" in notif_data:
            data["notification_summary"] = BaseSummary.deserialize(notif_data)

        return super().deserialize(data)

    def to_message(self, title: str = "📊 Отчёт о синхронизации расписания") -> str:
        """Формирует красивый текстовый отчёт по пайплайну."""

        def _format_section(
            section_title: str,
            data: Optional[Dict[str, Any]],
            format_fn: Callable[[Dict[str, Any]], List[str]],
        ) -> str:
            """Вспомогательная функция для форматирования секции."""
            if data:
                return f"{section_title}:\n" + "\n".join(format_fn(data))
            return f"{title}: \nнет данных"

        sections = [
            (
                "🕷 Scrapy",
                self.spider_result,
                lambda d: [
                    f"всего страниц/групп: {d.get('total_groups', '?')}",
                    f"пропущено: {d.get('skipped', '?')}",
                    f"обработано: {d.get('parsed', '?')}",
                    f"повторных: {d.get('no_change', '?')}",
                    f"ошибок: {d.get('errors', '?')}",
                    f"получено уроков: {d.get('total_lessons', '?')}",
                    f"статус: {d.get('closing_reason', '?')}",
                ],
            ),
            (
                "💾 Синхронизация уроков",
                self.sync_summary,
                lambda d: [
                    f"создано: {len(d.get('added', []))}",
                    f"обновлено: {len(d.get('updated', []))}",
                    f"удалено: {len(d.get('removed', []))}",
                ],
            ),
            (
                "📢 Отправка уведомлений",
                self.notification_summary.model_dump() if isinstance(self.notification_summary, BaseSummary)
                else self.notification_summary,
                lambda d: [
                    f"успешно={d.get('success_count', 0)}",
                    f"ошибки={d.get('failed_count', 0)}",
                    f"заблокировано={len(d.get('blocked_chat_ids', []))}",
                ],
            ),
        ]

        parts = [_format_section(t, d, f) for t, d, f in sections]
        if self.publication:
            p = self.publication
            parts.append('\n'.join([
                '📄 Публикация TableParser:',
                f"выгрузка: {escape(p.get('captured_at') or 'дата не указана')}",
                f"версия: № {p['revision_number']}",
                f"статус: {p['status']}",
                f"период: {p['start']} — {p['end'] or 'без верхней границы'}",
                f"занятий требуют ревью: {p['needs_review_count']}",
            ]))
            if p.get('notifications_status') == 'skipped':
                parts.append('Уведомления: этап пропущен, доставка не подтверждена.')
            if p.get('url'):
                parts.append(f'<a href="{escape(p["url"], quote=True)}">Открыть публикацию</a>')
        return f"{title}\n\n" + "\n\n".join(parts)
