"""Inclusive lesson synchronization bounds, resolved in the project timezone."""

from dataclasses import dataclass
from datetime import date, timedelta

from django.utils import timezone


@dataclass(frozen=True)
class LessonSyncRange:
    start: date
    end: date | None = None

    def __post_init__(self):
        if type(self.start) is not date or (self.end is not None and type(self.end) is not date):
            raise ValueError("Lesson sync boundaries must be dates")
        if self.end is not None and self.end < self.start:
            raise ValueError("end_date cannot be earlier than start_date")

    @classmethod
    def from_offsets(
        cls, *, start_day_offset: int = 0, end_day_offset: int | None = None,
    ) -> "LessonSyncRange":
        for name, value in (("start_day_offset", start_day_offset), ("end_day_offset", end_day_offset)):
            if value is None and name == "end_day_offset":
                continue
            if type(value) is not int:
                raise ValueError(f"{name} must be an integer")
        today = timezone.localdate()
        try:
            start = today + timedelta(days=start_day_offset)
            end = today + timedelta(days=end_day_offset) if end_day_offset is not None else None
        except OverflowError as exc:
            raise ValueError("Lesson sync offsets exceed the supported date range") from exc
        return cls(start, end)

    @property
    def cache_scope(self) -> str:
        return f"{self.start.isoformat()}:{self.end.isoformat() if self.end else 'unbounded'}:"

    def to_dict(self) -> dict[str, str | None]:
        """Return JSON-compatible boundaries, independent of task argument names."""
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
        }

    @classmethod
    def from_dict(cls, payload: dict) -> "LessonSyncRange":
        if not isinstance(payload, dict) or set(payload) != {"start", "end"}:
            raise ValueError("Invalid resolved lesson sync range")
        try:
            start = date.fromisoformat(payload["start"])
            end = date.fromisoformat(payload["end"]) if payload["end"] is not None else None
        except (TypeError, ValueError) as exc:
            raise ValueError("Invalid resolved lesson sync dates") from exc
        return cls(start, end)

    def contains(self, day: date) -> bool:
        return day >= self.start and (self.end is None or day <= self.end)
