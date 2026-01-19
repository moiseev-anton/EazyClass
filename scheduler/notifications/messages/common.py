from datetime import date as Date

WEEKDAY_SHORT_RU = ("ПН", "ВТ", "СР", "ЧТ", "ПТ", "СБ", "ВС")
WEEKDAYS_RU = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресение")
MONTHS_RU = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря"
)


def format_date_full_ru(date: Date) -> str:
    """Возвращает дату в формате 'Понедельник 17.11.2000'."""
    weekday = WEEKDAYS_RU[date.weekday()]
    return f"{weekday} {date:%d.%m.%Y}"


def format_date_short_ru(d: Date) -> str:
    """Возвращает дату в формате 'ПН, 17 ноября'."""
    weekday = WEEKDAY_SHORT_RU[d.weekday()]
    month = MONTHS_RU[d.month - 1]
    return f"{weekday}, {d.day} {month}"


def replace_digits_to_emojis(value) -> str:
    """
    Заменяет все цифры в переданном значении на emoji-цифры.

    Пример:
        "1 два 3" -> "1️⃣ два 3️⃣"
    """
    s = str(value)
    return "".join(f"{ch}\ufe0f\u20e3" if ch.isdigit() else ch for ch in s)
