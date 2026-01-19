from typing import Any, Callable, Dict, List, Optional, Union

from scheduler.dtos.summary_dtos.base_summary_dto import BaseSummary, register_summary


@register_summary
class PipelineSummary(BaseSummary):
    """Сводный отчёт по этапам пайплайна (скрапинг/парсинг → синхронизация → уведомления)."""

    spider_result: Optional[dict] = None
    sync_summary: Optional[dict] = None
    notification_summary: Optional[Union[dict, BaseSummary]] = None

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
                "groups": self.spider_result.get("groups_count"),
                "lessons": self.spider_result.get("lessons_count"),
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
                "🕷 Spider",
                self.spider_result,
                lambda d: [
                    f"группы: {d.get('groups_count', '?')}",
                    f"уроки: {d.get('lessons_count', '?')}",
                ],
            ),
            (
                "📘 Sync",
                self.sync_summary,
                lambda d: [
                    f"добавлено: {len(d.get('added', []))}",
                    f"обновлено: {len(d.get('updated', []))}",
                    f"удалено: {len(d.get('removed', []))}",
                ],
            ),
            (
                "📢 Notifier",
                self.notification_summary,
                lambda d: [
                    f"успешно={d.get('success_count', 0)}",
                    f"ошибки={d.get('failed_count', 0)}",
                    f"заблокировано={len(d.get('blocked_chat_ids', []))}",
                ],
            ),
        ]

        parts = [_format_section(t, d, f) for t, d, f in sections]
        return f"{title}\n\n" + "\n\n".join(parts)
