import logging

from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import (
    InlineKeyboardBuilder,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from cachetools.func import ttl_cache

from telegrambot.cache import CacheManager
from telegrambot.config import settings

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 86400  # 24 часа
KEYBOARD_ROW_WIDTH = 4
TEACHER_KEYBOARD_ROW_WIDTH = 2
GROUP_KEYBOARD_ROW_WIDTH = 2
CHAR_KEYBOARD_ROW_WIDTH = 4
FACULTIES_KEYBOARD_ROW_WIDTH = 1


class FacultyCallback(CallbackData, prefix="f"):
    key: str


class CourseCallback(CallbackData, prefix="c"):
    key: str


class GroupCallback(CallbackData, prefix="g"):
    id: str


class AlphabetCallback(CallbackData, prefix="a"):
    letter: str


class TeacherCallback(CallbackData, prefix="t"):
    id: str


class Button:
    _emoji_nums = {
        "0": "0️⃣",
        "1": "1️⃣",
        "2": "2️⃣",
        "3": "3️⃣",
        "4": "4️⃣",
        "5": "5️⃣",
        "6": "6️⃣",
        "7": "7️⃣",
        "8": "8️⃣",
        "9": "9️⃣",
    }

    home = InlineKeyboardButton(text="🏠 На главную", callback_data="main")
    phone = InlineKeyboardButton(text="📞 Поделиться номером", request_contact=True)

    today = InlineKeyboardButton(text="Сегодня", callback_data="schedule_today")
    tomorrow = InlineKeyboardButton(text="Завтра", callback_data="schedule_tomorrow")
    ahead = InlineKeyboardButton(text="Предстоящее", callback_data="schedule_ahead")
    week = InlineKeyboardButton(text="Неделя", callback_data="week_schedule")

    subgroup = InlineKeyboardButton(text="Подгруппа", callback_data="choose_subgroup")
    groups = InlineKeyboardButton(text="🎓Группы", callback_data="faculties")
    teachers = InlineKeyboardButton(
        text="👨‍🏫👩‍🏫Преподаватели", callback_data="alphabet"
    )
    notifications = InlineKeyboardButton(
        text="🔔Уведомления", callback_data="notifications"
    )
    site = InlineKeyboardButton(text="🌍Сайт", url=settings.base_link)

    context_schedule = InlineKeyboardButton(
        text="🗓️ Расписание", callback_data="schedule_context"
    )
    subscribe = InlineKeyboardButton(text="⭐ Подписаться", callback_data="subscribe")

    back = InlineKeyboardButton(text="◀️ Назад", callback_data="back")

    main_menu = [
        [groups, teachers],
        [notifications],
        [site],
    ]

    schedule_menu = [[today, tomorrow], [ahead, week]]

    subscribe_menu = [[subscribe], [home]]

    @classmethod
    def replace_with_emojis(cls, text: str):
        """Заменяет все цифры в строке на эмодзи"""
        return "".join(cls._emoji_nums.get(char, char) for char in text)

    @classmethod
    def course(cls, text: str):
        """Создаёт кнопку курса с эмодзи."""
        return InlineKeyboardButton(
            text=f"\t\t{cls.replace_with_emojis(text)}\t\t",
            callback_data=CourseCallback(key=text).pack(),
        )

    @classmethod
    def letter(cls, text: str):
        """Создаёт кнопку курса с эмодзи."""
        return InlineKeyboardButton(
            text=f"\t\t{text}\t\t", callback_data=AlphabetCallback(letter=text).pack()
        )


class KeyboardManager:
    home = InlineKeyboardMarkup(inline_keyboard=[[Button.home]])
    phone_request = InlineKeyboardMarkup(
        inline_keyboard=[[Button.phone], [Button.home]]
    )
    main_base = InlineKeyboardMarkup(inline_keyboard=Button.main_menu)
    main_teacher = InlineKeyboardMarkup(
        inline_keyboard=(Button.schedule_menu + Button.main_menu)
    )
    main_group = InlineKeyboardMarkup(
        inline_keyboard=(Button.schedule_menu + [[Button.subgroup]] + Button.main_menu)
    )
    subscribe = InlineKeyboardMarkup(inline_keyboard=Button.subscribe_menu)
    extend_subscribe = InlineKeyboardMarkup(
        inline_keyboard=[[Button.context_schedule]] + Button.subscribe_menu
    )

    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager

    @ttl_cache(maxsize=1, ttl=60 * 30)
    def get_faculties_keyboard(self) -> InlineKeyboardMarkup:
        """Собирает клавиатуру факультетов из кэша."""
        builder = InlineKeyboardBuilder()
        for faculty_key, faculty in self.cache_manager.faculties.items():
            builder.button(
                text=faculty.get("short_title", "-"),
                callback_data=FacultyCallback(key=faculty_key).pack(),
            )
        if self.cache_manager.faculties:
            builder.adjust(3)  # # до 2 факультетов в строке
        builder.row(Button.home)
        return builder.as_markup()

    @ttl_cache(maxsize=128, ttl=60 * 10)
    def get_courses_keyboard(self, faculty_id: str) -> InlineKeyboardMarkup:
        """
        Клавиатура курсов для выбранного факультета
        """
        builder = InlineKeyboardBuilder()
        courses = self.cache_manager.get_faculty_courses(faculty_id)

        for course_key in courses.keys():
            builder.add(Button.course(course_key))

        builder.row(Button.back, Button.home)
        return builder.as_markup()

    @ttl_cache(maxsize=128, ttl=60 * 10)
    def get_groups_keyboard(self, faculty_id: str, course: str) -> InlineKeyboardMarkup:
        """Собирает клавиатуру групп для выбранного факультета и курса."""
        builder = InlineKeyboardBuilder()
        groups = self.cache_manager.get_course(faculty_id, course)

        for group_id, group in groups.items():
            builder.button(
                text=group.get("title", "-"),
                callback_data=GroupCallback(id=group_id).pack(),
            )

        if groups:
            builder.adjust(2)  # до 2 групп в строке

        builder.row(Button.back, Button.home)
        return builder.as_markup()

    @ttl_cache(maxsize=1, ttl=60 * 30)
    def get_alphabet_keyboard(self) -> InlineKeyboardMarkup:
        """Собирает клавиатуру с буквами алфавита из teachers_cache."""
        builder = InlineKeyboardBuilder()
        letters = self.cache_manager.get_alphabet()

        for letter in letters:
            builder.add(Button.letter(letter))

        if letters:
            builder.adjust(5)  # 5 букв в ряд
        builder.row(Button.home)
        return builder.as_markup()

    @ttl_cache(maxsize=33, ttl=60 * 10)
    def get_teachers_keyboard(self, letter: str) -> InlineKeyboardMarkup:
        """Собирает клавиатуру учителей для выбранной буквы."""
        builder = InlineKeyboardBuilder()
        teachers = self.cache_manager.get_teachers_by_letter(letter)

        for teacher_id, teacher in teachers.items():
            builder.button(
                text=teacher.get("short_name", "-"),
                callback_data=TeacherCallback(id=teacher_id).pack(),
            )

        if teachers:
            if len(teachers) > 10:
                builder.adjust(2)
            else:
                builder.adjust(1)  # 1 учитель в ряд
        builder.row(Button.back, Button.home)
        return builder.as_markup()
