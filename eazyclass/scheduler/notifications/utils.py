from scheduler.models import Lesson


def format_group_lesson_message(lessons: list[Lesson]) -> str:
    if not lessons:
        return "Нет предстоящих уроков."

    # заголовок
    group_title = lessons[0].group.title
    parts = ["Предстоящее занятие 📚 \n" f"группа <b>{group_title}</b>"]

    # формируем блок для каждого урока
    for lesson in lessons:
        number = f"{lesson.period.lesson_number}\ufe0f\u20e3"
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
    start_time = lesson.period.start_time.strftime("%H:%M")
    classroom = getattr(lesson.classroom, "title", "—")
    subject = getattr(lesson.subject, "title", "—")
    teacher = getattr(lesson.teacher, "short_name", "—")
    group = getattr(lesson.group, "title", "—")
    subgroup = f"({lesson.subgroup} подгруппа)" if lesson.subgroup != "0" else ""

    return (
        f"Предстоящее занятие 📚\n"
        f"преподаватель <b>{teacher}</b>\n"
        "<blockquote>"
        f"{number} {start_time}  📍 {classroom}\n"
        f"<b>{subject}</b>\n"
        f"<i>{group}</i>\n"
        f"<i>{subgroup}</i>"
        "</blockquote>"
    )
