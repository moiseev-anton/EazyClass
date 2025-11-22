from pydantic import Field

from scheduler.dtos.summary_dtos.base_summary_dto import BaseSummary, register_summary


@register_summary
class NotificationSummary(BaseSummary):
    """Отчёт об отправке уведомлений."""

    success_count: int = 0
    failed_count: int = 0
    blocked_chat_ids: list[int | str] = Field(default_factory=list)

    def format_report(self, title: str = "📢 Уведомления") -> str:
        lines = [
            f"{title}:",
            f"✅ успешно: {self.success_count}",
            f"❌ ошибки: {self.failed_count}",
        ]

        if self.blocked_chat_ids:
            lines.append(f"🚫 заблокировано: {len(self.blocked_chat_ids)}")

        return "\n".join(lines)


@register_summary
class StartNotificationSummary(NotificationSummary):
    """Отчёт по уведомлениям о начале уроков."""

    period_str: str = ""
    lessons_count: int = 0
    notifications_count: int = 0

    def format_report(self, title: str = "📚 Уведомления о занятиях") -> str:
        if self.lessons_count == 0:
            return f"{title}:" f"Период: {self.period_str}" f"Уроков найдено: {self.lessons_count}"

        lines = [
            f"{title}:",
            f"Период: {self.period_str}",
            f"Уроков найдено: {self.lessons_count}",
            f"Уведомлений подготовлено: {self.notifications_count}",
        ]

        if base := super().format_report().strip():
            lines.append(base)

        return "\n".join(lines)

    def merge_from(self, notif: NotificationSummary) -> None:
        """Переносит поля из NotificationSummaryDTO в себя."""
        self.success_count = notif.success_count
        self.failed_count = notif.failed_count
        self.blocked_chat_ids = notif.blocked_chat_ids.copy()
