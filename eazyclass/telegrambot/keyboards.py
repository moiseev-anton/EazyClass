import hashlib
import json
from collections import defaultdict

from django.core.cache import caches
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

from .services import KeyboardDataService

CACHE_TIMEOUT = 86400  # 24 часа
KEYBOARD_ROW_WIDTH = 4
TEACHER_KEYBOARD_ROW_WIDTH = 2

cache = caches['telegrambot_cache']

emoji = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
         '5': '5️⃣', '6': '6️⃣', '7': '7️⃣', '8': '8️⃣', '9': '9️⃣'}

# Учителя 👨‍🏫👩‍🏫
# Группы 🎓
# 📌📖 📅 🕜 📚 🔔🔕

keyboards = {}
static_keyboards = {}
context_data_store = {}

# Кнопки
home_button = InlineKeyboardButton("🏠 На главную", callback_data="home")
phone_button = InlineKeyboardButton("Поделиться номером", request_contact=True)
today_button = InlineKeyboardButton("На сегодня", callback_data="schedule_today")
tomorrow_button = InlineKeyboardButton("На завтра", callback_data="schedule_tomorrow")
from_today_button = InlineKeyboardButton("Актуальное", callback_data="from_today")
week_button = InlineKeyboardButton("На неделю", callback_data="week_schedule")
subgroup_button = InlineKeyboardButton("Подгруппа", callback_data="choose_subgroup")
groups_button = InlineKeyboardButton("🎓Группы", callback_data="faculties")
teachers_button = InlineKeyboardButton("👨‍🏫👩‍🏫Преподаватели", callback_data="teachers")
notifications_button = InlineKeyboardButton("🔔Уведомления", callback_data="notifications")
site_button = InlineKeyboardButton("🌍Сайт", url='https://bincol.ru/rasp/')

context_schedule_button = InlineKeyboardButton("Расписание", callback_data="schedule_context")
subscribe_button = InlineKeyboardButton("Подписаться", callback_data="subscribe")


# Статические клавиатуры
home_base_keyboard = InlineKeyboardMarkup()
home_base_keyboard.add(today_button, tomorrow_button)
home_base_keyboard.add(from_today_button, week_button)
home_base_keyboard.add(groups_button)
home_base_keyboard.add(teachers_button)
home_base_keyboard.add(notifications_button)
home_base_keyboard.add(site_button)
static_keyboards['home_base'] = home_base_keyboard

home_group_keyboard = InlineKeyboardMarkup()
home_group_keyboard.add(today_button, tomorrow_button)
home_group_keyboard.add(from_today_button, week_button)
home_group_keyboard.add(subgroup_button)
home_group_keyboard.add(groups_button)
home_group_keyboard.add(teachers_button)
home_group_keyboard.add(notifications_button)
home_group_keyboard.add(site_button)
static_keyboards['home_group'] = home_group_keyboard

home_short_keyboard = InlineKeyboardMarkup()
home_short_keyboard.add(groups_button)
home_short_keyboard.add(teachers_button)
home_short_keyboard.add(notifications_button)
home_short_keyboard.add(site_button)
static_keyboards['home_short'] = home_short_keyboard

# Клавиатура start
start_keyboard = InlineKeyboardMarkup()
start_keyboard.row(home_button)
static_keyboards['start'] = start_keyboard


phone_request_keyboard = InlineKeyboardMarkup()
phone_request_keyboard.add(phone_button)
phone_request_keyboard.add(home_button)
static_keyboards['phone_request'] = phone_request_keyboard

subscribe_keyboard = InlineKeyboardMarkup()
subscribe_keyboard.add(context_schedule_button)
subscribe_keyboard.add(subscribe_button)
subscribe_keyboard.add(home_button)
static_keyboards['subscribe'] = subscribe_keyboard


# Динамические клавиатуры
def get_keyboard(key: str):
    keyboard = keyboards.get(key)
    if not keyboard:
        update_dynamic_keyboards()
        keyboard = keyboards[key]
    return keyboard


def get_teacher_keyboards():
    new_keyboards = {}
    new_context_data_store = {}
    teachers = KeyboardDataService.get_data_for_dynamic_keyboard('Teacher')
    button_sets = defaultdict(list)
    for teacher_id, short_name in teachers:
        initial = short_name[0].upper()
        initial_key = f'initial:{initial}'
        context_data = {'model': 'Teacher', 'id': teacher_id, 'title': short_name}
        context_hash = generate_hash(context_data)
        teacher_key = f'context:{context_hash}'
        new_context_data_store[teacher_key] = context_data
        if initial_key not in button_sets:
            initial_button = InlineKeyboardButton(text=f"\t{initial}\t", callback_data=initial_key)
            button_sets['teachers'].append(initial_button)
        teacher_button = InlineKeyboardButton(text=short_name, callback_data=teacher_key)
        button_sets[initial_key].append(teacher_button)

    new_keyboards['teachers'] = build_keyboard(button_sets.pop('teachers'))

    for key, button_set in button_sets.items():
        new_keyboards[key] = build_keyboard(button_set, row_width=TEACHER_KEYBOARD_ROW_WIDTH)

    return new_keyboards


def build_keyboard(buttons: list[InlineKeyboardButton], row_width: int = KEYBOARD_ROW_WIDTH) -> InlineKeyboardMarkup:
    keyboard = InlineKeyboardMarkup(row_width=row_width)

    keyboard.add(*buttons)

    keyboard.row(home_button)
    return keyboard


def get_group_keyboards():
    new_keyboards = {}
    groups = KeyboardDataService.get_data_for_dynamic_keyboard('Group')
    button_sets = defaultdict(list)
    for group_id, title, grade, faculty_title in groups:
        grade_key = f'grade:{faculty_title}:{grade}'
        faculty_key = f'faculty:{faculty_title}'
        context_data = {'model': 'Group', 'id': group_id, 'title': title}
        context_hash = generate_hash(context_data)
        group_key = f'context:{context_hash}'
        context_data_store[group_key] = context_data

        if faculty_key not in button_sets:
            faculty_button = InlineKeyboardButton(text=faculty_title, callback_data=faculty_key)
            button_sets['faculties'].append(faculty_button)

        if grade_key not in button_sets:
            grade_button = InlineKeyboardButton(text=f'\t{emoji[grade]}\t', callback_data=grade_key)
            button_sets[faculty_key].append(grade_button)

        group_button = InlineKeyboardButton(text=title, callback_data=group_key)
        button_sets[grade_key].append(group_button)

    for key, button_set in button_sets.items():
        new_keyboards[key] = build_keyboard(button_set)

    return new_keyboards


def update_dynamic_keyboards():
    global keyboards
    global context_data_store
    # Инициализация нового словаря контекста
    context_data_store = {}

    keyboards = get_group_keyboards()
    keyboards.update(get_teacher_keyboards())
    keyboards.update(static_keyboards)


# Вспомогательная функция
def generate_hash(data: dict) -> str:
    """Генерирует хеш для данных контекста."""
    data_string = json.dumps(data, sort_keys=True)
    return hashlib.md5(data_string.encode()).hexdigest()
