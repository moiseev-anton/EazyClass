from scheduler.models import Lesson
from .common import format_date_full_ru, replace_digits_to_emojis


def format_for_group(lessons: list[Lesson]) -> str:
    """Генерирует текст уведомления о начале занятия для учебной группы.
    Занятий может быть несколько, так как группы могут быть разделены на подгруппы.
    Как правило, 1-2 занятия в сообщении.

    Пример:
        "Предстоящее занятие 🔔
         Понедельник 10.10.2010
         <blockquote>
         1️⃣ 08:00  📍 2203
         Математика
         Иванова И.И.
         <i>(1 подгруппа)</i> <- опционально
         </blockquote>"
    """
    if not lessons:
        return "Нет предстоящих уроков."

    date_str = format_date_full_ru(lessons[0].period.date)
    parts = [
        "Предстоящее занятие 🔔",
        f"{date_str}",
    ]

    # формируем отдельные блоки для каждого занятия
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


def format_for_teacher(lesson: Lesson) -> str:
    """Генерирует текст уведомления о начале занятия для преподавателя группы.

        "Предстоящее занятие 🔔
         Понедельник 10.10.2010
         <blockquote>
         1️⃣ 08:00  📍 2203
         Математика
         32 ГРПП
         <i>(1 подгруппа)</i> <- опционально
         </blockquote>"
    """

    number = f"{lesson.period.lesson_number}\ufe0f\u20e3"
    date_str = format_date_full_ru(lesson.period.date)
    start_time = lesson.period.start_time.strftime("%H:%M")
    classroom = getattr(lesson.classroom, "title", "—")
    subject = getattr(lesson.subject, "title", "—")
    group = getattr(lesson.group, "title", "—")
    subgroup = f"({lesson.subgroup} подгруппа)" if lesson.subgroup != "0" else ""

    return (
        f"Предстоящее занятие 🔔 \n"
        f"{date_str}\n"
        "<blockquote>"
        f"{number} {start_time}  📍 {classroom}\n"
        f"<b>{subject}</b>\n"
        f"<i>{group}</i>\n"
        f"<i>{subgroup}</i>"
        "</blockquote>"
    )
