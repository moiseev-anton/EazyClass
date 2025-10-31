from dataclasses import dataclass, field
from typing import List, Set


@dataclass(slots=True)
class NotificationItem:
    message: str
    destinations: List[int | str]  # chat_id или user_id

@dataclass(slots=True)
class NotificationSummary:
    success_count: int = 0
    failed_count: int = 0
    blocked_chat_ids: set[int] = field(default_factory=set)

    def as_dict(self) -> dict:
        return {
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "blocked_chat_ids": list(self.blocked_chat_ids),
        }

    def __str__(self):
        return (
            f"✅ {self.success_count} успешно, "
            f"❌ {self.failed_count} с ошибками, "
            f"🚫 {len(self.blocked_chat_ids)} заблокировали."
        )
