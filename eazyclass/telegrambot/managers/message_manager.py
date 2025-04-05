import logging
from typing import Dict, Any

from telegrambot.cache import CacheRepository

logger = logging.getLogger(__name__)


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
    GROUP_SELECTED = "Вы выбрали группу: {group_title}\nСсылка: {group_link}"
    ERROR_DEFAULT = "⚠ Что-то пошло не так, попробуйте снова."

    ALPHABET_PROMPT = "Выберите букву:"
    TEACHERS_PROMPT = "Выберите преподавателя:"
    TEACHER_SELECTED = "Вы выбрали преподавателя: {teacher_full_name}"

    def __init__(self, cache_repository: CacheRepository):
        self.cache_repository = cache_repository

    @classmethod
    def get_start_message(
        cls, user: Dict[str, Any], created: bool, nonce_status: str | None
    ) -> str:
        """Собирает финальное сообщение в зависимости от условий"""
        auth_message = cls.AUTH_MESSAGES.get(nonce_status, "")

        if not created and auth_message:
            return auth_message

        name = user.get("first_name", "")
        welcome = (
            cls.WELCOME_NEW.format(name=name)
            if created
            else cls.WELCOME_BACK.format(name=name)
        )
        return welcome + (f"\n\n{auth_message}" if auth_message else "")

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

    def get_group_selected_message(
        self, faculty_id: str, course_id: str, group_id: str
    ) -> str:
        """Сообщение после выбора группы."""
        group = self.cache_repository.get_group(faculty_id, course_id, group_id)
        if not group:
            return "Ошибка: группа не найдена."
        return self.GROUP_SELECTED.format(
            group_title=group.get("title", "-"), group_link=group.get("link", "")
        )

    @classmethod
    def get_alphabet_message(cls) -> str:
        return cls.ALPHABET_PROMPT

    @classmethod
    def get_teachers_message(cls, letter: str) -> str:
        return cls.TEACHERS_PROMPT.format(letter=letter)

    def get_teacher_selected_message(self, letter: str, teacher_id: str) -> str:
        teacher = self.cache_repository.get_teacher(letter, teacher_id)
        if not teacher:
            return "Ошибка: преподаватель не найден."
        return self.TEACHER_SELECTED.format(
            teacher_full_name=teacher.get("full_name", "-")
        )

    @classmethod
    def get_error_message(cls) -> str:
        """Возвращает стандартное сообщение об ошибке с клавиатурой 'На главную'."""
        return cls.ERROR_DEFAULT
