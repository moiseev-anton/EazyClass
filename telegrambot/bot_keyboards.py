import json
from collections import defaultdict

from django.core.cache import caches
from django.db.models import Prefetch
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from ..scheduler.models import Faculty, Group, Teacher
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
weekend_button = InlineKeyboardButton("До конца недели", callback_data="end_schedule")
week_button = InlineKeyboardButton("На неделю", callback_data="week_schedule")
subgroup_button = InlineKeyboardButton("Подгруппа", callback_data="choose_subgroup")
groups_button = InlineKeyboardButton("🎓Группы", callback_data="faculties")
teacher_button = InlineKeyboardButton("👨‍🏫👩‍🏫Преподаватели", callback_data="choose_teacher")
notifications_button = InlineKeyboardButton("🔔Уведомления", callback_data="notifications")
site_button = InlineKeyboardButton("🌍Сайт", callback_data="visit_site")

subscribe_teacher_button = InlineKeyboardButton("Подписаться", callback_data="subscribe_teacher")

# Статические клавиатуры
home_teacher_keyboard = InlineKeyboardMarkup()
home_teacher_keyboard.add(today_button, tomorrow_button)
home_teacher_keyboard.add(weekend_button, week_button)
home_teacher_keyboard.add(groups_button)
home_teacher_keyboard.add(teacher_button)
home_teacher_keyboard.add(notifications_button)
home_teacher_keyboard.add(site_button)

home_group_keyboard = InlineKeyboardMarkup()
home_group_keyboard.add(today_button, tomorrow_button)
home_group_keyboard.add(weekend_button, week_button)
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


# def get_structure():
#     structure = {}
#     faculties = Faculty.objects.filter(is_active=True).prefetch_related(
#         Prefetch(
#             'groups',
#             queryset=Group.objects.filter(is_active=True).order_by('grade', 'title'),
#             to_attr='active_groups'
#         )
#     ).order_by('short_title')
#
#     for faculty in faculties:
#         faculty_data = {}
#         for group in faculty.active_groups:
#             if group.grade not in faculty_data:
#                 faculty_data[group.grade] = {}
#             faculty_data[group.grade][group.title] = group.id
#         structure[faculty.short_title] = faculty_data
#     # Теперь мы кешируем клавиатуры и нет необходимости кешировать данные для клавиатур
#     # cache.set('faculty_structure', json.dumps(structure), timeout=CACHE_TIMEOUT)
#     return structure


# Динамические клавиатуры
def generate_faculty_keyboard(faculties: list[str]):
    keyboard = InlineKeyboardMarkup()
    button_list = []
    for faculty in faculties:
        button = InlineKeyboardButton(text=faculty, callback_data=f'f:{faculty}')
        button_list.append(button)
    while button_list:
        keyboard.row(*button_list[:4])
        button_list = button_list[4:]

    keyboard.add(home_button)
    return keyboard


def generate_course_keyboard(faculty: str, courses: dict):
    keyboard = InlineKeyboardMarkup()
    button_list = []

    for course in courses:
        button = InlineKeyboardButton(text=f"     {emoji[course]}     ", callback_data=f'c:{faculty}:{course}')
        button_list.append(button)

    while button_list:
        keyboard.row(*button_list[:4])
        button_list = button_list[4:]

    keyboard.add(home_button)
    return keyboard


def generate_group_keyboard(groups: list[dict]):
    keyboard = InlineKeyboardMarkup()
    button_list = []
    for group in groups:
        button = InlineKeyboardButton(text=group['title'], callback_data=f'g:{group["id"]}')
        button_list.append(button)
    while button_list:
        keyboard.row(*button_list[:4])
        button_list = button_list[4:]

    keyboard.add(home_button)
    return keyboard


def get_keyboard(key: str):
    keyboard = keyboard_cache.get(key)
    if not keyboard:
        pass
        # TODO: Надо подумать нужна ли эта проверка. У нас может не быть активных факультетов (летом либо из-за ошибки)
        # вдругих же случаях предполагаю что если мы получили некий ключ то значит и дальнейшие данные тоже должны были быть
    return keyboard


def generate_initials_keyboard():
    initials = get_cached_teachers()
    keyboard = InlineKeyboardMarkup()
    button_list = []
    # Создаем кнопки для каждой буквы
    for initial in sorted(initials.keys()):
        button = InlineKeyboardButton(text=initial, callback_data=f"initial:{initial}")
        button_list.append(button)
    while button_list:
        keyboard.row(*button_list[:4])
        button_list = button_list[4:]

    keyboard.add(home_button)
    return keyboard


def generate_teachers_keyboard(initial: str):
    teachers = get_cached_teachers()[initial]
    keyboard = InlineKeyboardMarkup()
    button_list = []
    # Создаем кнопки для каждой буквы
    for teacher in teachers:
        button = InlineKeyboardButton(text=teacher['short_name'], callback_data=f"teacher:{teacher['id']}")
        button_list.append(button)
    while button_list:
        keyboard.row(*button_list[:4])
        button_list = button_list[4:]

    keyboard.add(home_button)
    return keyboard


def get_teachers():
    teachers_data = Teacher.objects.filter(is_active=True).values_list('id', 'short_name')
    teachers = defaultdict(list)
    for teacher_id, short_name in teachers_data:
        initial = short_name[0].upper()
        teacher_data = {'short_name': short_name, 'id': teacher_id}
        teachers[initial].append(teacher_data)
    return teachers




def get_faculties():
    faculties = Faculty.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            'groups',
            queryset=Group.objects.filter(is_active=True).order_by('grade', 'title'),
            to_attr='active_groups'
        )
    ).order_by('short_title')

    return faculties


def build_keyboard(buttons: list[InlineKeyboardButton]):
    keyboard = InlineKeyboardMarkup()

    while buttons:
        keyboard.row(*buttons[:KEYBOARD_ROW_WIDTH])
        buttons = buttons[KEYBOARD_ROW_WIDTH:]

    keyboard.add(home_button)
    return keyboard


def update_keyboard_cache():
    faculties = get_faculties()
    faculty_buttons = []

    for faculty in faculties:
        faculty_title = faculty.short_title
        faculty_button = InlineKeyboardButton(text=faculty_title, callback_data=f'f:{faculty_title}')
        faculty_buttons.append(faculty_button)
        group_buttons_by_grade = defaultdict(list)
        for group in faculty.active_groups:
            group_button = InlineKeyboardButton(text=group.title, callback_data=f'g:{group.id}')
            group_buttons_by_grade[group.grade].append(group_button)
        grade_buttons = []
        for grade, group_buttons in group_buttons_by_grade.items():
            grade_button = InlineKeyboardButton(text=f"\t{emoji[grade]}\t", callback_data=f'c:{faculty_title}:{grade}')
            grade_buttons.append(grade_button)
            group_keyboard = build_keyboard(group_buttons)
            keyboard_cache[f'c:{faculty_title}:{grade}'] = group_keyboard

        grade_keyboard = build_keyboard(grade_buttons)
        keyboard_cache[f'f:{faculty_title}'] = grade_keyboard

    faculties_keyboard = build_keyboard(faculty_buttons)
    keyboard_cache['faculties'] = faculties_keyboard


