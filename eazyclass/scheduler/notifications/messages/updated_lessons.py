from typing import Iterable
from datetime import date as Date

from .common import format_date_short_ru

MAX_VISIBLE_DATES = 6
DATE_LINE_TEMPLATE = "\t\t • {d}"
DATE_LINES_OMITTED_TEMPLATE = "\t\t  … и ещё {n} {days}"

def format_date_lines(dates: Iterable[Date], limit: int = 0) -> str:
    """
    Формирует многострочную строку дат.
    Например:
        • СР, 20 ноября
        • ЧТ, 21 ноября
        … и ещё 2 дня
    """
    dates = sorted(set(dates))
    shown = dates[:limit] if limit > 0 else dates
    lines = [
        DATE_LINE_TEMPLATE.format(d=format_date_short_ru(d))
        for d in shown
    ]

    if limit and len(dates) > limit:
        n = len(dates) - limit
        plural_days = "день" if n == 1 else "дня" if 2 <= n <= 4 else "дней"
        omitted = DATE_LINES_OMITTED_TEMPLATE.format(n=n, days=plural_days)
        lines.append(omitted)

    return "\n".join(lines)


def format_lessons_updated_message(name: str, dates: list[Date]) -> str:
    """
    Формирует текст уведомления об изменении расписания.

    Например:
        🗓️ {name}
        <b><u>РАСПИСАНИЕ ОБНОВЛЕНО</u></b>
        Обновленные дни:
        <i>• СР, 20 ноября
        • ЧТ, 21 ноября
        … и ещё 2 дня</i>
    """
    date_lines = format_date_lines(dates, limit=MAX_VISIBLE_DATES)
    return (
        f"🗓️ {name}"
        f"<b><u>РАСПИСАНИЕ ОБНОВЛЕНО</u></b>\n"
        f"Обновленные дни:\n"
        f"<i>{date_lines}</i>\n"
    )
