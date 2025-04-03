import logging

from aiogram.filters.callback_data import CallbackData
from aiogram.utils.keyboard import InlineKeyboardBuilder, InlineKeyboardButton, InlineKeyboardMarkup
from telegrambot.config import settings
from telegrambot.cache import cache_manager


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
    id: int


class AlphabetCallback(CallbackData, prefix="a"):
    letter: str


class TeacherCallback(CallbackData, prefix="t"):
    id: int


class Buttons:
    _emoji_nums = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
                   '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'}

    home = InlineKeyboardButton(text="🏠 На главную", callback_data="main")
    phone = InlineKeyboardButton(text="📞 Поделиться номером", request_contact=True)

    today = InlineKeyboardButton(text="Сегодня", callback_data="schedule_today")
    tomorrow = InlineKeyboardButton(text="Завтра", callback_data="schedule_tomorrow")
    ahead = InlineKeyboardButton(text="Предстоящее", callback_data="schedule_ahead")
    week = InlineKeyboardButton(text="Неделя", callback_data="week_schedule")

    subgroup = InlineKeyboardButton(text="Подгруппа", callback_data="choose_subgroup")
    groups = InlineKeyboardButton(text="🎓Группы", callback_data="faculties")
    teachers = InlineKeyboardButton(text="👨‍🏫👩‍🏫Преподаватели", callback_data="alphabet")
    notifications = InlineKeyboardButton(text="🔔Уведомления", callback_data="notifications")
    site = InlineKeyboardButton(text="🌍Сайт", url=settings.base_link)

    context_schedule = InlineKeyboardButton(text="🗓️ Расписание", callback_data="schedule_context")
    subscribe = InlineKeyboardButton(text="⭐ Подписаться", callback_data="subscribe")

    back = InlineKeyboardButton(text="◀️ Назад", callback_data="back")

    main_menu = [
        [groups, teachers],
        [notifications],
        [site],
    ]

    schedule_menu = [
        [today, tomorrow],
        [ahead, week]
    ]

    subscribe_menu = [
        [subscribe],
        [home]
    ]

    @classmethod
    def replace_with_emojis(cls, text: str):
        """Заменяет все цифры в строке на эмодзи"""
        return ''.join(cls._emoji_nums.get(char, char) for char in text)

    @classmethod
    def course(cls, text: str):
        """Создаёт кнопку курса с эмодзи."""
        return InlineKeyboardButton(
            text=f"\t\t{cls.replace_with_emojis(text)}\t\t",
            callback_data=CourseCallback(key=text).pack()
        )

    @classmethod
    def letter(cls, text: str):
        """Создаёт кнопку курса с эмодзи."""
        return InlineKeyboardButton(
            text=f"\t\t{text}\t\t",
            callback_data=AlphabetCallback(letter=text).pack()
        )


class KeyboardManager:
    home = InlineKeyboardMarkup(inline_keyboard=[[Buttons.home]])
    phone_request = InlineKeyboardMarkup(inline_keyboard=[[Buttons.phone], [Buttons.home]])
    main_base = InlineKeyboardMarkup(inline_keyboard=Buttons.main_menu)
    main_teacher = InlineKeyboardMarkup(inline_keyboard=(Buttons.schedule_menu + Buttons.main_menu))
    main_group = InlineKeyboardMarkup(
        inline_keyboard=(Buttons.schedule_menu + [[Buttons.subgroup]] + Buttons.main_menu)
    )
    subscribe = InlineKeyboardMarkup(inline_keyboard=Buttons.subscribe_menu)
    extend_subscribe = InlineKeyboardMarkup(inline_keyboard=[[Buttons.context_schedule]] + Buttons.subscribe_menu)

    @staticmethod
    def get_faculties_keyboard() -> InlineKeyboardMarkup:
        """Собирает клавиатуру факультетов из кэша."""
        builder = InlineKeyboardBuilder()
        for faculty_key, faculty in cache_manager.faculties.items():
            builder.button(
                text=faculty.get("short_title", '-'),
                callback_data=FacultyCallback(key=faculty_key).pack()
            )
        if cache_manager.faculties:
            builder.adjust(3)  # # до 2 факультетов в строке
        builder.row(Buttons.home)
        return builder.as_markup()

    @staticmethod
    def get_courses_keyboard(faculty_id: str) -> InlineKeyboardMarkup:
        """
        Клавиатура курсов для выбранного факультета
        """
        builder = InlineKeyboardBuilder()
        faculty = cache_manager.faculties.get(faculty_id, {})
        courses = faculty.get("courses", {})

        for course_key in courses.keys():
            builder.add(Buttons.course(course_key))

        builder.row(Buttons.back, Buttons.home)
        return builder.as_markup()

    @staticmethod
    def get_groups_keyboard(faculty_id: str, course: str) -> InlineKeyboardMarkup:
        """Собирает клавиатуру групп для выбранного факультета и курса."""
        builder = InlineKeyboardBuilder()
        faculty = cache_manager.faculties.get(faculty_id, {})
        courses = faculty.get("courses", {})
        groups = courses.get(course, [])

        for group in groups:
            builder.button(
                text=group.get("title", "-"),
                callback_data=GroupCallback(id=group["id"]).pack()
            )

        if groups:
            builder.adjust(2)  # до 2 групп в строке

        builder.row(Buttons.back, Buttons.home)
        return builder.as_markup()

    @staticmethod
    def get_alphabet_keyboard() -> InlineKeyboardMarkup:
        """Собирает клавиатуру с буквами алфавита из teachers_cache."""
        builder = InlineKeyboardBuilder()
        for letter in cache_manager.get_alphabet():
            builder.add(Buttons.letter(letter))
        if cache_manager.teachers:
            builder.adjust(5)  # 5 букв в ряд
        builder.row(Buttons.home)
        return builder.as_markup()

    @staticmethod
    def get_teachers_keyboard(letter: str) -> InlineKeyboardMarkup:
        """Собирает клавиатуру учителей для выбранной буквы."""
        builder = InlineKeyboardBuilder()
        teachers = cache_manager.get_teachers_by_letter(letter)

        for teacher in teachers:
            builder.button(
                text=teacher.get("short_name", "-"),
                callback_data=TeacherCallback(id=teacher["id"]).pack()
            )

        if teachers:
            if len(teachers) > 10:
                builder.adjust(2)
            else:
                builder.adjust(1)  # 1 учитель в ряд
        builder.row(Buttons.back, Buttons.home)
        return builder.as_markup()



