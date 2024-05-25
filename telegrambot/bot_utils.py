import json

from django.core.cache import caches
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from eazyclass.scheduler.models import Faculty, Group
from django.db.models import Prefetch

KEYBOARD_TIMEOUT = 86400  # 24 часа
KEYBOARD_ROW_WIDTH = 4

cache = caches['telegrambot_cache']

emoji = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
         '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'}

home_button = InlineKeyboardButton("🏠 На главную", callback_data="home")


def cache_structure():
    structure = {}
    faculties = Faculty.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            'groups',
            queryset=Group.objects.filter(is_active=True).order_by('grade', 'title'),
            to_attr='active_groups'
        )
    ).order_by('short_title')

    for faculty in faculties:
        faculty_data = {}
        for group in faculty.active_groups:
            if group.grade not in faculty_data:
                faculty_data[group.grade] = []
            faculty_data[group.grade].append({
                'title': group.title,
                'id': group.id
            })
        structure[faculty.short_title] = faculty_data
    cache.set('faculty_structure', json.dumps(structure), timeout=KEYBOARD_TIMEOUT)


def get_cached_structure():
    structure = cache.get('faculty_structure')
    if structure:
        return json.loads(structure)
    else:
        cache_structure()
        return json.loads(cache.get('faculty_structure'))


def generate_faculty_keyboard():
    structure = get_cached_structure()
    keyboard = InlineKeyboardMarkup()
    button_list = []
    for faculty_name in structure:
        button = InlineKeyboardButton(text=faculty_name, callback_data=f'f:{faculty_name}')
        button_list.append(button)
    while button_list:
        keyboard.row(*button_list[:4])
        button_list = button_list[4:]

    keyboard.add(home_button)
    return keyboard


def generate_course_keyboard(faculty):
    structure = get_cached_structure()
    faculty_data = structure.get(faculty, {})
    keyboard = InlineKeyboardMarkup()
    for course in faculty_data:
        button = InlineKeyboardButton(text=f"     {emoji[course]}     ", callback_data=f'c:{faculty}:{course}')
        keyboard.add(button)

    keyboard.add(home_button)
    return keyboard


def generate_group_keyboard(faculty_name, course):
    structure = get_cached_structure()
    faculty_data = structure.get(faculty_name, {})
    groups = faculty_data.get(course, [])
    keyboard = InlineKeyboardMarkup()
    button_list = []
    for group in groups:
        button = InlineKeyboardButton(text=group['title'], callback_data=f'group:{group["id"]}')
        button_list.append(button)
    while button_list:
        keyboard.row(*button_list[:4])
        button_list = button_list[4:]

    keyboard.add(home_button)
    return keyboard


