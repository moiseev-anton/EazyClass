from dataclasses import dataclass
from typing import List, Set


@dataclass(slots=True)
class NotificationItem:
    message: str
    destinations: List[int]  # chat_id или user_id

@dataclass(slots=True)
class NotificationSummary:
    success_count: int = 0
    failed_count: int = 0
    blocked_chat_ids: Set[int] = None

    def __post_init__(self):
        if self.blocked_chat_ids is None:
            self.blocked_chat_ids = set()