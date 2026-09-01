from enums import LessonDisplayMode
from scheduler.models import Lesson
from .common import format_date_full_ru, format_time, replace_digits_to_emojis


def format_lesson(lesson: Lesson, mode: LessonDisplayMode = LessonDisplayMode.FULL) -> str:
    period = lesson.period
    number_emoji = replace_digits_to_emojis(period.lesson_number)
    part = f" | {replace_digits_to_emojis(period.part)}" if period.part else ""
    start = format_time(period.start_time)
    end = format_time(period.end_time)

    lines = [
        f"{number_emoji}<b>{part} {start} - {end}</b> 📍{lesson.classroom or '---'}",
        f"<b>{lesson.subject}</b>",
    ]

    if LessonDisplayMode.SHOW_SUBGROUP in mode and lesson.subgroup and lesson.subgroup != "0":
        lines.append(f"{lesson.subgroup} подгруппа")

    if LessonDisplayMode.SHOW_GROUP in mode and lesson.group:
        lines.append(f"<i>{lesson.group.title}</i>")

    if LessonDisplayMode.SHOW_TEACHER in mode and lesson.teacher:
        lines.append(f"<i>{lesson.teacher.short_name}</i>")

    return "\n".join(lines)


def format_start_lesson_message(
    lessons: list[Lesson],
    mode: LessonDisplayMode = LessonDisplayMode.FULL
) -> str:
    if not lessons:
        return "Нет предстоящих уроков."

    date_str = format_date_full_ru(lessons[0].period.date)
    parts = [
        "Предстоящее занятие 🔔",
        f"{date_str}",
    ]

    for lesson in sorted(lessons, key=lesson_sort_key):
        parts.append(f"<blockquote>"
                     f"{format_lesson(lesson, mode=mode)}"
                     f"</blockquote>")

    return "\n".join(parts)


def format_group_start_message(lessons: list[Lesson]):
    return format_start_lesson_message(
        lessons,
        mode=LessonDisplayMode.FOR_GROUP,
    )


def format_teacher_start_message(lessons: list[Lesson]):
    return format_start_lesson_message(
        lessons,
        mode=LessonDisplayMode.FOR_TEACHER,
    )


def lesson_sort_key(lesson: Lesson) -> tuple[str, str, int]:
    subgroup = str(lesson.subgroup or "0")

    return (
        lesson.group.title if lesson.group else "",
        subgroup,
        lesson.pk or 0,
    )
