from datetime import date as Date

from scheduler.models import Lesson


WEEKDAYS_RU = [
    "Понедельник", "Вторник", "Среда",
    "Четверг", "Пятница", "Суббота", "Воскресение"
]

def format_date_verbose(date: Date) -> str:
    """Возвращает дату в формате '7 ноября (ПТ)'."""
    weekday = WEEKDAYS_RU[date.weekday()]
    return f"{weekday} {date.strftime("%d.%m.%Y")}"

def replace_digits_to_emojis(value) -> str:
    s = str(value)
    return "".join(f"{ch}\ufe0f\u20e3" if ch.isdigit() else ch for ch in s)

def format_group_lesson_message(lessons: list[Lesson]) -> str:
    if not lessons:
        return "Нет предстоящих уроков."

    # group_title = lessons[0].group.title
    date_str = format_date_verbose(lessons[0].period.date)
    parts = [
        "Предстоящее занятие 🔔",
        # f"группа <b>{group_title}</b>",
        f"{date_str}"
    ]

    # формируем блок для каждого урока
    for lesson in lessons:
        number = f"{replace_digits_to_emojis(lesson.period.lesson_number)}"
        start_time = lesson.period.start_time.strftime("%H:%M")
        classroom = getattr(lesson.classroom, "title", "—")
        subject = getattr(lesson.subject, "title", "—")
        teacher = getattr(lesson.teacher, "short_name", "—")
        subgroup = f"<i>({lesson.subgroup} подгруппа)</i>" if lesson.subgroup != "0" else ""

        parts.append(
            "<blockquote>"
            f"{number} {start_time}  📍 {classroom}\n"
            f"<b>{subject}</b>\n"
            f"<i>{teacher}</i>\n"
            f"{subgroup}"
            "</blockquote>"
        )
    return "\n".join(parts)


def format_teacher_lesson_message(lesson: Lesson) -> str:
    number = f"{lesson.period.lesson_number}\ufe0f\u20e3"
    date_str = format_date_verbose(lesson.period.date)
    start_time = lesson.period.start_time.strftime("%H:%M")
    classroom = getattr(lesson.classroom, "title", "—")
    subject = getattr(lesson.subject, "title", "—")
    # teacher = getattr(lesson.teacher, "short_name", "—")
    group = getattr(lesson.group, "title", "—")
    subgroup = f"({lesson.subgroup} подгруппа)" if lesson.subgroup != "0" else ""

    return (
        f"Предстоящее занятие 🔔 \n"
        # f"преподаватель <b>{teacher}</b>\n"
        f"{date_str}\n"
        "<blockquote>"
        f"{number} {start_time}  📍 {classroom}\n"
        f"<b>{subject}</b>\n"
        f"<i>{group}</i>\n"
        f"<i>{subgroup}</i>"
        "</blockquote>"
    )
