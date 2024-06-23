import json
from collections import defaultdict

from django.core.cache import caches
from django.db.models import Prefetch, QuerySet
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from scheduler.models import Faculty, Group, Teacher
from cachetools import LRUCache

CACHE_TIMEOUT = 86400  # 24 часа
KEYBOARD_ROW_WIDTH = 4

cache = caches['telegrambot_cache']
keyboard_cache = LRUCache(maxsize=100)

emoji = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
         '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'}

# Учителя 👨‍🏫👩‍🏫
# Группы 🎓
# 📌📖 📅 🕜 📚 🔔🔕


# Кнопки
home_button = InlineKeyboardButton("🏠 На главную", callback_data="home")
today_button = InlineKeyboardButton("На сегодня", callback_data="schedule_today")
tomorrow_button = InlineKeyboardButton("На завтра", callback_data="schedule_tomorrow")
from_today_button = InlineKeyboardButton("Актуальное", callback_data="from_today")
week_button = InlineKeyboardButton("На неделю", callback_data="week_schedule")
subgroup_button = InlineKeyboardButton("Подгруппа", callback_data="choose_subgroup")
groups_button = InlineKeyboardButton("🎓Группы", callback_data="faculties")
teacher_button = InlineKeyboardButton("👨‍🏫👩‍🏫Преподаватели", callback_data="teachers")
notifications_button = InlineKeyboardButton("🔔Уведомления", callback_data="notifications")
site_button = InlineKeyboardButton("🌍Сайт", callback_data="visit_site")

subscribe_teacher_button = InlineKeyboardButton("Подписаться", callback_data="subscribe_teacher")

# Статические клавиатуры
home_teacher_keyboard = InlineKeyboardMarkup()
home_teacher_keyboard.add(today_button, tomorrow_button)
home_teacher_keyboard.add(from_today_button, week_button)
home_teacher_keyboard.add(groups_button)
home_teacher_keyboard.add(teacher_button)
home_teacher_keyboard.add(notifications_button)
home_teacher_keyboard.add(site_button)

home_group_keyboard = InlineKeyboardMarkup()
home_group_keyboard.add(today_button, tomorrow_button)
home_group_keyboard.add(from_today_button, week_button)
home_group_keyboard.add(subgroup_button)
home_group_keyboard.add(groups_button)
home_group_keyboard.add(teacher_button)
home_group_keyboard.add(notifications_button)
home_group_keyboard.add(site_button)

short_home_keyboard = InlineKeyboardMarkup()
short_home_keyboard.add(groups_button)
short_home_keyboard.add(teacher_button)
short_home_keyboard.add(notifications_button)
short_home_keyboard.add(site_button)

# Клавиатура start
start_keyboard = InlineKeyboardMarkup()
start_keyboard.row(home_button, site_button)


# Динамические клавиатуры
def get_keyboard(key: str):
    keyboard = keyboard_cache.get(key)
    if not keyboard:
        pass
        # TODO: Надо подумать нужна ли эта проверка. У нас может не быть активных факультетов (летом либо из-за ошибки)
        # вдругих же случаях предполагаю что если мы получили некий ключ то значит и дальнейшие данные тоже должны были быть
    return keyboard


def update_teacher_keyboard_cache():
    teachers = Teacher.objects.filter(is_active=True).values_list('id', 'short_name')
    teacher_buttons_by_initials = defaultdict(list)
    for teacher_id, short_name in teachers:
        teacher_button = InlineKeyboardButton(text=short_name, callback_data=f't:{teacher_id}')
        initial = short_name[0].upper()
        teacher_buttons_by_initials[initial].append(teacher_button)

    initial_buttons = []
    for initial, teacher_buttons in teacher_buttons_by_initials.items():
        initial_button = InlineKeyboardButton(text=f"\t{initial}\t", callback_data=f'initial:{initial}')
        initial_buttons.append(initial_button)
        teacher_keyboard = build_keyboard(teacher_buttons)
        keyboard_cache[f'initial:{initial}'] = teacher_keyboard

    initial_keyboard = build_keyboard(initial_buttons)
    keyboard_cache[f'teachers'] = initial_keyboard


def get_faculties():
    return Faculty.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            'groups',
            queryset=Group.objects.filter(is_active=True).order_by('grade', 'title'),
            to_attr='active_groups'
        )
    ).order_by('short_title')


def build_keyboard(buttons: list[InlineKeyboardButton], row_width: int = KEYBOARD_ROW_WIDTH) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup()

    for i in range(0, len(buttons), row_width):
        keyboard.row(*buttons[i:i + row_width])

    keyboard.add(home_button)
    return keyboard


def update_group_keyboard_cache():
    faculties = get_faculties()
    faculty_buttons = []

    for faculty in faculties:
        if not faculty.active_groups:
            continue
        faculty_title = faculty.short_title
        faculty_button = InlineKeyboardButton(text=faculty_title, callback_data=f'faculty:{faculty_title}')
        faculty_buttons.append(faculty_button)
        group_buttons_by_grade = defaultdict(list)
        for group in faculty.active_groups:
            group_button = InlineKeyboardButton(text=group.title, callback_data=f'group:{group.id}')
            group_buttons_by_grade[group.grade].append(group_button)
        grade_buttons = []
        for grade, group_buttons in group_buttons_by_grade.items():
            grade_button = InlineKeyboardButton(text=f"\t{emoji[grade]}\t",
                                                callback_data=f'grade:{faculty_title}:{grade}')
            grade_buttons.append(grade_button)
            group_keyboard = build_keyboard(group_buttons)
            keyboard_cache[f'grade:{faculty_title}:{grade}'] = group_keyboard

        grade_keyboard = build_keyboard(grade_buttons)
        keyboard_cache[f'faculty:{faculty_title}'] = grade_keyboard

    faculties_keyboard = build_keyboard(faculty_buttons)
    keyboard_cache['faculties'] = faculties_keyboard


def get_active_groups() -> QuerySet:
    """
    Получает список всех активных групп с основной информацией.

    Выполняет запрос к базе данных, чтобы получить значения идентификаторов групп,
    их названий, курса и краткого названия факультета для каждой активной группы,
    упорядоченные по названию факультета и курсу.

    Returns:
        QuerySet: Список кортежей, где каждый кортеж содержит (id, title, grade, faculty__short_title).

    """
    try:
        return Group.objects.filter(is_active=True).values_list(
            'id', 'title', 'grade', 'faculty__short_title'
        ).order_by('faculty__short_title', 'grade', 'title')
    except Exception as e:
        # Логирование ошибки, если запрос не удаётся выполнить
        # logger.error(f"Ошибка при получении активных групп: {e}")
        raise


# def organize_structure_data():
#     groups = get_active_groups()
#     structure = defaultdict(lambda: defaultdict(list))
#     for group_id, title, grade, faculty_title in groups:
#         structure[faculty_title][grade].append((group_id, title))


def update_group_keyboard_cache2():
    groups = get_active_groups()
    button_sets = defaultdict(list)
    for group_id, title, grade, faculty_title in groups:
        grade_key = f'grade:{faculty_title}:{grade}'
        faculty_key = f'faculty:{faculty_title}'
        group_key = f'group:{group_id}'

        if faculty_key not in button_sets:
            faculty_button = InlineKeyboardButton(text=faculty_title, callback_data=faculty_key)
            button_sets['faculties'].append(faculty_button)

        if grade_key not in button_sets:
            grade_button = InlineKeyboardButton(text=grade, callback_data=grade_key)
            button_sets[faculty_key].append(grade_button)

        group_button = InlineKeyboardButton(text=title, callback_data=group_key)
        button_sets[grade_key].append(group_button)

    for key, button_set in button_sets.items():
        keyboard_cache[key] = build_keyboard(button_set)
