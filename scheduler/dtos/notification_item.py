from dataclasses import dataclass
from typing import List


@dataclass(slots=True)
class NotificationItem:
    message: str
    destinations: List[int | str]  # chat_id или user_id
