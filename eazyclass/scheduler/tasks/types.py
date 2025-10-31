from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class UpdatePipelineContext:
    spider_result: Optional[dict] = None
    sync_summary: Optional[dict] = None
    notification_summary: Optional[dict] = None

    def format_report(self) -> str:
        """Генерирует текст отчёта о выполнении задач."""

        def _format_section(
            title: str, data: Optional[Dict], format_fn: Callable[[Dict], List[str]]
        ) -> str:
            """Вспомогательная функция для форматирования секции."""
            if data:
                return f"{title}: \n" + "\n".join(format_fn(data))
            return f"{title}: \nнет данных\n"

        sections = [
            (
                "🕷 Spider",
                self.spider_result,
                lambda d: [
                    f"группы={d.get('groups_count', '?')}",
                    f"уроки={d.get('lessons_count', '?')}",
                ],
            ),
            (
                "📘 Sync",
                self.sync_summary,
                lambda d: [
                    f"добавлено={len(d.get('added', []))}",
                    f"обновлено={len(d.get('updated', []))}",
                    f"удалено={len(d.get('removed', []))}",
                ],
            ),
            (
                "📢 Notifier",
                self.notification_summary,
                lambda d: [
                    f"успешно={d.get('success_count', 0)}",
                    f"ошибки={d.get('failed_count', 0)}",
                    f"заблокировали={len(d.get('blocked_chat_ids', []))}",
                ],
            ),
        ]

        parts = [_format_section(title, data, fmt) for title, data, fmt in sections]
        return "📊 Отчёт о синхронизации расписания:\n\n" + "\n\n".join(parts)
