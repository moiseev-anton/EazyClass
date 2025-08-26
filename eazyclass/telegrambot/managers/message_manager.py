import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any

from jsonapi_client.resourceobject import ResourceObject

from telegrambot.cache import CacheRepository

logger = logging.getLogger(__name__)


@dataclass
class Period:
    lesson_number: int
    date: str
    start_time: str
    end_time: str


@dataclass
class Teacher:
    id: int
    full_name: str
    short_name: str


@dataclass
class Lesson:
    period: Period
    group: str
    subgroup: str
    subject: str
    classroom: str
    teacher: Teacher

    def __post_init__(self):
        # Преобразуем строковые данные в объекты Period и Teacher
        if isinstance(self.period, dict):
            self.period = Period(**self.period)
        if isinstance(self.teacher, dict):
            self.teacher = Teacher(**self.teacher)

    def format_time(self) -> str:
        """Форматирует время урока"""
        return self.period.start_time[:5]  # HH:MM

    def format_subgroup(self) -> str:
        """Форматирует подгруппу (если есть)"""
        return f"{self.subgroup} подгруппа" if self.subgroup != "0" else None

    def format_for_group(self) -> str:
        """Форматирует урок для отображения в групповом расписании"""
        lines = [
            f"{self._get_emoji()}  <b>{self.format_time()}</b>   📍{self.classroom or '-'}",
            f"<b>{self.subject}</b>",
            self.format_subgroup(),
            f"<i>{self.teacher.short_name}</i>" if self.teacher else None
        ]
        return "\n".join(filter(None, lines))

    def format_for_teacher(self) -> str:
        """Форматирует урок для отображения в преподавательском расписании"""
        lines = [
            f"{self._get_emoji()}  <b>{self.format_time()}</b>   📍{self.classroom or '-'}",
            f"<b>{self.subject}</b>",
            self.format_subgroup(),
            f"<i>{self.group}</i>"
        ]
        return "\n".join(filter(None, lines))

    def _get_emoji(self) -> str:
        """Возвращает эмодзи для номера урока"""
        emoji_map = {
            1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
            5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣"
        }
        return emoji_map.get(self.period.lesson_number, str(self.period.lesson_number))


class ScheduleMessageBuilder:
    """Класс для построения сообщений с расписанием"""

    _WEEKDAYS_RU = {
        0: "ПОНЕДЕЛЬНИК",
        1: "ВТОРНИК",
        2: "СРЕДА",
        3: "ЧЕТВЕРГ",
        4: "ПЯТНИЦА",
        5: "СУББОТА",
        6: "ВОСКРЕСЕНЬЕ"
    }

    @classmethod
    def _format_date(cls, date_str: str) -> str:
        """Форматирует дату: Понедельник ДД.ММ.ГГГГ"""
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        day_name = cls._WEEKDAYS_RU[date_obj.weekday()]
        date_formatted = date_obj.strftime("%d.%m.%Y")
        return f"<b>{day_name}</b> {date_formatted}"

    @classmethod
    def build_schedule(
            cls,
            title: str,
            schedule_data: Dict[str, Any],
            for_teacher: bool = False
    ) -> str:
        """Строит сообщение с расписанием"""
        if "error" in schedule_data:
            return "⚠️ Ошибка при получении расписания"

        if not schedule_data.get("data"):
            return "📅 Занятий нет"

        message_lines = [f"🗓️ <b>{title}</b>", ""]

        for day in schedule_data["data"]:
            message_lines.append(cls._format_date(day["date"]))

            # Создаем объекты Lesson и форматируем их
            lessons = [Lesson(**lesson_data) for lesson_data in day["lessons"]]
            formatted_lessons = [
                lesson.format_for_teacher() if for_teacher else lesson.format_for_group()
                for lesson in lessons
            ]

            message_lines.append(f"<blockquote>{'\n\n'.join(formatted_lessons)}</blockquote>")
            message_lines.append("")

        # Убираем последнюю пустую строку
        return "\n".join(message_lines[:-1])


class MessageManager:
    WELCOME_NEW = "Добро пожаловать, {name}!👋\nРегистрация выполнена успешно."
    WELCOME_BACK = "С возвращением, {name}! 👋"

    AUTH_MESSAGES = {
        "authenticated": "✅ Вы успешно авторизовались, теперь можно вернуться обратно ↩",
        "failed": "⚠ Произошла ошибка авторизации, повторите попытку позже.",
    }

    FACULTIES_PROMPT = "Выберите факультет:"
    COURSES_PROMPT = "{faculty_title}\n\nВыберите курс:"
    GROUPS_PROMPT = "{faculty_title}\n{course_id} курс\n\nВыберите группу:"
    GROUP_SELECTED = "Группа: {group_title}"
    ERROR_DEFAULT = "⚠ Что-то пошло не так, попробуйте снова."

    ALPHABET_PROMPT = "Выберите букву:"
    TEACHERS_PROMPT = "Выберите преподавателя:"
    TEACHER_SELECTED = "Преподаватель: {teacher_full_name}"

    def __init__(self, cache_repository: CacheRepository):
        self.cache_repository = cache_repository

    @classmethod
    def get_start_message(cls, user_resource: ResourceObject) -> str:
        """Формирует стартовое сообщение для пользователя."""

        user_meta = getattr(user_resource, "meta", {})
        created = getattr(user_meta, "created", False)
        nonce_status = getattr(user_meta, "nonceStatus")

        auth_message = cls.AUTH_MESSAGES.get(nonce_status, "")

        if not created and auth_message:
            return auth_message

        name = getattr(user_resource, "first_name", "Anonymous")
        welcome = (
            cls.WELCOME_NEW.format(name=name)
            if created
            else cls.WELCOME_BACK.format(name=name)
        )

        return f"{welcome}\n\n{auth_message}" if auth_message else welcome

    @classmethod
    def get_faculties_message(cls) -> str:
        """Сообщение для выбора факультета."""
        return cls.FACULTIES_PROMPT

    def get_courses_message(self, faculty_id: str) -> str:
        """Сообщение для выбора курса с указанием факультета."""
        faculty_title = self.cache_repository.get_faculty(faculty_id).get(
            "title", "Неизвестный факультет"
        )
        return self.COURSES_PROMPT.format(faculty_title=faculty_title)

    def get_groups_message(self, faculty_id: str, course_id: str) -> str:
        """Сообщение для выбора группы с указанием факультета и курса."""
        faculty_title = self.cache_repository.get_faculty(faculty_id).get(
            "title", "Неизвестный факультет"
        )
        return self.GROUPS_PROMPT.format(
            faculty_title=faculty_title, course_id=course_id
        )

    def get_group_selected_message(self, group: Dict[str, Any]) -> str:
        """Сообщение после выбора группы."""
        return self.GROUP_SELECTED.format(group_title=group.get("title", "-"))

    @classmethod
    def get_alphabet_message(cls) -> str:
        return cls.ALPHABET_PROMPT

    @classmethod
    def get_teachers_message(cls, letter: str) -> str:
        return cls.TEACHERS_PROMPT.format(letter=letter)

    def get_teacher_selected_message(self, teacher_data: Dict[str, Any]) -> str:
        return self.TEACHER_SELECTED.format(
            teacher_full_name=teacher_data.get("full_name", "-")
        )

    @classmethod
    def get_error_message(cls) -> str:
        """Возвращает стандартное сообщение об ошибке с клавиатурой 'На главную'."""
        return cls.ERROR_DEFAULT

    @staticmethod
    def format_group_schedule(group_title: str, schedule_data: Dict[str, Any]) -> str:
        """Форматирует расписание для группы"""
        return ScheduleMessageBuilder.build_schedule(group_title, schedule_data)

    @staticmethod
    def format_teacher_schedule(teacher_name: str, schedule_data: Dict[str, Any]) -> str:
        """Форматирует расписание для преподавателя"""
        return ScheduleMessageBuilder.build_schedule(teacher_name, schedule_data, for_teacher=True)
