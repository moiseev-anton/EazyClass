import json
import logging
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import List, Callable, Dict, Optional

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from django.db.models import QuerySet

# from scheduler.models import Group, Teacher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 86400  # 24 часа
KEYBOARD_ROW_WIDTH = 4
TEACHER_KEYBOARD_ROW_WIDTH = 2
GROUP_KEYBOARD_ROW_WIDTH = 2
CHAR_KEYBOARD_ROW_WIDTH = 4
FACULTIES_KEYBOARD_ROW_WIDTH = 1


class Buttons:
    emoji = {'0': '0️⃣', '1': '1️⃣', '2': '2️⃣', '3': '3️⃣', '4': '4️⃣',
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
    site = InlineKeyboardButton(text="🌍Сайт", url='https://bincol.ru/rasp/')

    context_schedule = InlineKeyboardButton(text="🗓️ Расписание", callback_data="schedule_context")
    subscribe = InlineKeyboardButton(text="⭐ Подписаться", callback_data="subscribe")

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


class DynamicKeyboardManager:
    api_endpoint = "bot-faculties/"
    cache_file = "cached_data.json"
    cached_data = None

    @classmethod
    def load_initial_cache(cls):
        """Загрузка данных из файла при инициализации"""
        if os.path.exists(cls.cache_file):
            with open(cls.cache_file, "r") as f:
                cls.cached_data = json.load(f)
            logger.info("Кэш загружен из файла")
        else:
            logger.info("Файл кэша не найден, требуется обновление")

    async def fetch_schedule_data(self):
        """Запрос данных от API"""
        async with aiohttp.ClientSession() as session:
            async with session.get(self.api_url) as response:
                if response.status == 200:
                    return await response.json()
                logger.warning(f"Ошибка API: {response.status}")
                return None

    async def update_cache(self):
        """Обновление кэшированных данных"""
        new_data = await self.fetch_schedule_data()
        if new_data and isinstance(new_data, dict) and new_data:
            self.cached_data = new_data
            with open(self.cache_file, "w") as f:
                json.dump(new_data, f)
            logger.info("Кэш обновлён из API")
        else:
            logger.warning("Получены некорректные данные или ошибка API")

    def get_faculty_keyboard(self):
        """Построение клавиатуры факультетов"""
        if not self.cached_data:
            return None
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for faculty_id, faculty in self.cached_data.items():
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=faculty["title"], callback_data=f"faculty_{faculty_id}")
            ])
        return keyboard

    def get_course_keyboard(self, faculty_id):
        """Построение клавиатуры курсов"""
        if not self.cached_data or faculty_id not in self.cached_data:
            return None
        faculty = self.cached_data[faculty_id]
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for course in faculty["courses"].keys():
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=f"Курс {course}", callback_data=f"course_{course}")
            ])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back")])
        return keyboard

    def get_group_keyboard(self, faculty_id, course):
        """Построение клавиатуры групп"""
        if not self.cached_data or faculty_id not in self.cached_data:
            return None
        faculty = self.cached_data[faculty_id]
        if course not in faculty["courses"]:
            return None
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        for group in faculty["courses"][course]:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text=group["title"], callback_data=f"group_{group['id']}")
            ])
        keyboard.inline_keyboard.append([InlineKeyboardButton(text="Назад", callback_data="back")])
        return keyboard

    def is_data_available(self):
        """Проверка доступности данных"""
        return self.cached_data is not None and bool(self.cached_data)

    # _static_keyboards = {
    #     'home': InlineKeyboardMarkup(inline_keyboard=[[Buttons.home]]),
    #     'phone_request': InlineKeyboardMarkup(inline_keyboard=[[Buttons.phone], [Buttons.home]]),
    #     'main_base': InlineKeyboardMarkup(inline_keyboard=Buttons.main_menu),
    #     'main_teacher': InlineKeyboardMarkup(inline_keyboard=(Buttons.schedule_menu + Buttons.main_menu)),
    #     'main_group': InlineKeyboardMarkup(inline_keyboard=(
    #             Buttons.schedule_menu + [[Buttons.subscribe]] + Buttons.main_menu)
    #     ),
    #     'subscribe': InlineKeyboardMarkup(inline_keyboard=Buttons.subscribe_menu),
    #     'extend_subscribe': InlineKeyboardMarkup(inline_keyboard=[[Buttons.context_schedule]] + Buttons.subscribe_menu),
    # }



#     @classmethod
#     def build_teacher_keyboards(cls):
#         letter_button_callback_template = 'teacher:{letter}'
#         teacher_button_callback_template = 'view:Teacher:{teacher_id}'
#
#         new_keyboards = {}
#         teachers = (Teacher.objects.filter(is_active=True)
#                     .values_list('id', 'short_name')
#                     .order_by('short_name'))
#
#         button_sets = defaultdict(list)
#         for teacher_id, short_name in teachers:
#             letter = short_name[0].upper() if short_name else '-'
#             teacher_key = f'view:Teacher:{teacher_id}'
#             letter_key = f'teachers:{letter}'
#             if letter_key not in button_sets:
#                 letter_button = InlineKeyboardButton(text=f"\t{letter}\t", callback_data=letter_key)
#                 button_sets[cls.teachers_button.callback_data].append(letter_button)
#             teacher_button = InlineKeyboardButton(text=short_name, callback_data=teacher_key)
#             button_sets[letter_key].append(teacher_button)
#
#         new_keyboards['teachers'] = build_keyboard(button_sets.pop('teachers'))
#
#         for key, button_set in button_sets.items():
#             new_keyboards[key] = build_keyboard(button_set, row_width=TEACHER_KEYBOARD_ROW_WIDTH)
#
#         return new_keyboards
#
#     @classmethod
#     def get_view_keyboard(cls, entity: str, _id: int):
#         view_keyboard = quick_markup({
#             "📅 Просмотреть расписание": {'callback_data': f"schedule:{entity}:{_id}"},
#             "⭐ Подписаться": {'callback_data': f"subscribe:{entity}:{_id}"}
#         }, row_width=1)
#         view_keyboard.add(cls.home_button)
#         return view_keyboard
#
#
# @dataclass
# class KeyboardLayerConfig:
#     """Конфигурация для создания уровня клавиатуры"""
#     name: str
#     callback_prefix: str
#     group_by: Callable
#     text_func: Callable
#     callback_func: Callable
#     row_width: int = 1
#
#     extra_buttons: Optional[List[InlineKeyboardButton]] = None   # Дополнительные кнопки
#     # extra_buttons: Optional[List[Union[Tuple[str, str], InlineKeyboardButton]]] = field(default_factory=list)
#     """
#     Дополнительные кнопки в формате (текст, callback_data) или готовые объекты InlineKeyboardButton.
#     Можно использовать для "Назад" или других кнопок.
#     """
#
# class KeyboardEngine:
#     @classmethod
#     def build_hierarchical_keyboards(
#             cls,
#             data: QuerySet,
#             layers: List[KeyboardLayerConfig]
#     ) -> Dict[str, InlineKeyboardMarkup]:
#         """Универсальный билдер иерархических клавиатур"""
#         keyboards = {}
#
#         for layer in layers:
#             grouped_items = defaultdict(list)
#
#             # Группируем элементы по ключу
#             for item in data:
#                 group_key = layer.group_by(item)
#                 grouped_items[group_key].append(item)
#
#             # Создаем клавиатуры для каждой группы
#             for group_key, items in grouped_items.items():
#                 buttons = []
#                 seen = set()
#
#                 # Собираем уникальные кнопки
#                 for item in items:
#                     text = layer.text_func(item)
#                     callback = f"{layer.callback_prefix}:{layer.callback_func(item)}"
#                     if (text, callback) not in seen:
#                         buttons.append(
#                             InlineKeyboardButton(text=text, callback_data=callback)
#                         )
#                         seen.add((text, callback))
#
#                 # Сортируем кнопки по тексту
#                 buttons.sort(key=lambda b: b.text)
#
#                 # Создаем клавиатуру
#                 keyboard = InlineKeyboardMarkup(row_width=layer.row_width)
#                 keyboard.add(*buttons)
#
#                 # Добавляем кнопку "Назад" если определена
#                 if layer.back_button_func and items:
#                     try:
#                         # Берем первый элемент группы для генерации кнопки
#                         back_button = layer.back_button_func(items[0])
#                         keyboard.row(back_button)
#                     except Exception as e:
#                         logger.error(f"Error creating back button: {str(e)}")
#
#                 # Добавляем статические дополнительные кнопки
#                 if layer.extra_buttons:
#                     keyboard.row(*layer.extra_buttons)
#
#                 keyboards[f"{layer.name}:{group_key}"] = keyboard
#
#             return keyboards

        #     # Первоначальная группировка данных кнопок для слоя
        #     for item in data:
        #         group_key = layer.group_by(item)
        #         button_text = layer.text_func(item)
        #         button_callback = layer.callback_func(item)
        #         grouped_data[group_key].add((button_text, button_callback))
        #
        #     # Построение клавиатур для текущего слоя
        #     for group_key, button_set in grouped_data.items():
        #         grouped_buttons = [
        #             InlineKeyboardButton(text=text, callback_data=callback)
        #             for text, callback in sorted(button_set)  # Сортируем в алфавитном порядке по тексту кнопки
        #         ]
        #
        #         # Обрабатываем дополнительные кнопки
        #         extra_buttons = []
        #         for btn in layer.extra_buttons:
        #             if isinstance(btn, InlineKeyboardButton):
        #                 extra_buttons.append(btn)  # Уже готовая кнопка
        #             else:
        #                 text, callback = btn
        #                 extra_buttons.append(InlineKeyboardButton(text=text, callback_data=callback))
        #
        #         # Создаем финальную клавиатуру
        #         keyboards[group_key] = cls._build_keyboard(grouped_buttons, extra_buttons, row_width=layer.row_width)
        #
        # return keyboards

    # @staticmethod
    # def _build_keyboard(
    #         buttons: List[InlineKeyboardButton],
    #         extra_buttons: List[InlineKeyboardButton],
    #         row_width: int
    # ) -> InlineKeyboardMarkup:
    #     """Вспомогательный метод для сборки клавиатуры"""
    #     keyboard = InlineKeyboardMarkup(row_width=row_width)
    #
    #     # Добавляем основные кнопки по row_width
    #     keyboard.add(*buttons)
    #
    #     # Добавляем дополнительные кнопки отдельными рядами
    #     for extra_button in extra_buttons:
    #         keyboard.row(extra_button)
    #
    #     return keyboard
    #
    #
    # @staticmethod
    # def build_keyboard_layer(
    #         data,
    #         group_by_func,
    #         get_text_func,
    #         get_callback_data_func,
    #         row_width=1,
    # ):
    #     """
    #     Универсальная функция для создания одного слоя клавиатуры.
    #     """
    #     button_sets = defaultdict(set)  # Используем множество для исключения дубликатов
    #
    #     # Группируем объекты по ключу
    #     for item in data:
    #         group_key = group_by_func(item)  # Например, "letter:A", "faculty:IT"
    #         text = get_text_func(item)  # Текст кнопки
    #         callback_data = get_callback_data_func(item)  # Данные для callback
    #         button_sets[group_key].add((text, callback_data))  # Добавляем в множество
    #
    #     keyboards = {}
    #
    #     # Создаем клавиатуры для каждой группы
    #     for key, button_data in button_sets.items():
    #         keyboard = InlineKeyboardMarkup(row_width=row_width)
    #         buttons = [InlineKeyboardButton(text, callback_data=callback)
    #                    for text, callback in sorted(button_data)]
    #         keyboard.add(*buttons)
    #         keyboards[key] = keyboard
    #
    #     return keyboards
    #
    #
    #
    # @classmethod
    # def build_teachers_keyboards(cls):
    #     keyboards = {}
    #
    #     teachers = (
    #         Teacher.objects.filter(is_active=True)
    #         .values('id', 'short_name')
    #     )
    #
    #     # Строим клавиатуру Алфавитного указателя
    #     alphabet_keyboard = cls.build_keyboard_layer(
    #         data=teachers,
    #         group_by_func=lambda item: 'alphabet',
    #         get_text_func=lambda item: item[1][0] if item[1] else '-',
    #         get_callback_data_func=lambda item: f'teachers:{item[1][0] if item[1] else '-'}',
    #         row_width=CHAR_KEYBOARD_ROW_WIDTH,
    #     )
    #
    #     # Строим клавиатуры учителей группируя по первым буквам фамилии
    #     teachers_keyboards = cls.build_keyboard_layer(
    #         data=teachers,
    #         group_by_func=lambda item: f'teachers:{item[1][0] if item[1] else '-'}',
    #         get_text_func=lambda item: item[1] or '-',
    #         get_callback_data_func=lambda item: f'view:Teacher:{item[0]}',
    #         row_width=TEACHER_KEYBOARD_ROW_WIDTH,
    #     )
    #
    #     keyboards.update(alphabet_keyboard)
    #     keyboards.update(teachers_keyboards)
    #
    #     return keyboards
    #
    # @staticmethod
    # def _build_keyboard(buttons: list, row_width: int = 1) -> InlineKeyboardMarkup:
    #     """Вспомогательный метод для сборки клавиатуры"""
    #     keyboard = InlineKeyboardMarkup(row_width=row_width)
    #     keyboard.add(*buttons)
    #     return keyboard
    #
    # @classmethod
    # def build_groups_keyboards(cls):
    #     keyboards = {}
    #
    #     groups = (
    #         Group.objects.filter(is_active=True)
    #         .values('id', 'title', 'grade', 'faculty_id', 'faculty__short_title')
    #     )
    #
    #     # Строим клавиатуру Факультетов
    #     faculties_keyboard = cls.build_keyboard_layer(
    #         data=groups,
    #         name='faculties',
    #         group_by_func=lambda x: '',
    #         get_text_func=lambda x: x[3],
    #         callback_prefix='grades',
    #         get_callback_data_func=lambda x: f'grades:{x[1]}',
    #         row_width=FACULTIES_KEYBOARD_ROW_WIDTH,
    #     )
    #
    #     # Строим клавиатуры курсов группируя по факультетам
    #     grades_keyboards = cls.build_keyboard_layer(
    #         data=groups,
    #         name='grades',
    #         group_by_func=lambda item: f'grades:{item[3]}',
    #         get_text_func=lambda item: item[2],
    #         callback_prefix='groups',
    #         get_callback_data_func=lambda item: f'groups:{item[3]}:{item[2]}',
    #         row_width=CHAR_KEYBOARD_ROW_WIDTH,
    #     )
    #
    #     # Строим клавиатуры групп, группируя по курсам для каждого факультета
    #     groups_keyboards = cls.build_keyboard_layer(
    #         data=groups,
    #         name='groups',
    #         group_by_func=lambda item: f'groups:{item[3]}:{item[2]}',
    #         get_text_func=lambda item: item[1],
    #         callback_prefix='view:Group',
    #         get_callback_data_func=lambda item: f'view:Group:{item[0]}',
    #         row_width=GROUP_KEYBOARD_ROW_WIDTH,
    #     )
    #
    #     keyboards.update(faculties_keyboard)
    #     keyboards.update(grades_keyboards)
    #     keyboards.update(groups_keyboards)
    #
    #     return keyboards

    # @staticmethod
    # def build_keyboard(buttons: list[InlineKeyboardButton],
    #                    row_width: int = KEYBOARD_ROW_WIDTH
    #                    ) -> InlineKeyboardMarkup:
    #     keyboard = InlineKeyboardMarkup(row_width=row_width)
    #     keyboard.add(*buttons)
    #     return keyboard


# Учителя 👨‍🏫👩‍🏫
# Группы 🎓
# 📌📖 📅 🕜 📚 🔔🔕

# def build_keyboard(buttons: list[InlineKeyboardButton], row_width: int = KEYBOARD_ROW_WIDTH) -> InlineKeyboardMarkup:
#     keyboard = InlineKeyboardMarkup(row_width=row_width)
#
#     keyboard.add(*buttons)
#
#     keyboard.row(home_button)
#     return keyboard
#
# def get_teacher_keyboards():
#     new_keyboards = {}
#     new_context_data_store = {}
#     teachers = Teacher.objects.filter(is_active=True).values('id', 'short_name').order_by('short_name')
#     button_sets = defaultdict(list)
#     for teacher_id, short_name in teachers:
#         initial = short_name[0].upper()
#         initial_key = f'initial:{initial}'
#         context_data = {'model': 'Teacher', 'id': teacher_id, 'title': short_name}
#         context_hash = generate_hash(context_data)
#         teacher_key = f'context:{context_hash}'
#         new_context_data_store[teacher_key] = context_data
#         if initial_key not in button_sets:
#             initial_button = InlineKeyboardButton(text=f"\t{initial}\t", callback_data=initial_key)
#             button_sets['teachers'].append(initial_button)
#         teacher_button = InlineKeyboardButton(text=short_name, callback_data=teacher_key)
#         button_sets[initial_key].append(teacher_button)
#
#     new_keyboards['teachers'] = build_keyboard(button_sets.pop('teachers'))
#
#     for key, button_set in button_sets.items():
#         new_keyboards[key] = build_keyboard(button_set, row_width=TEACHER_KEYBOARD_ROW_WIDTH)
#
#     return new_keyboards
#
#
#
#
#
# def get_group_keyboards():
#     new_keyboards = {}
#     groups = (Group.objects.filter(is_active=True)
#               .values('id', 'title', 'grade', 'faculty__short_title')
#               .order_by('faculty__short_title', 'grade', 'title'))
#     button_sets = defaultdict(list)
#     for group_id, title, grade, faculty_title in groups:
#         grade_key = f'grade:{faculty_title}:{grade}'
#         faculty_key = f'faculty:{faculty_title}'
#         context_data = {'model': 'Group', 'id': group_id, 'title': title}
#         context_hash = generate_hash(context_data)
#         group_key = f'context:{context_hash}'
#         context_data_store[group_key] = context_data
#
#         if faculty_key not in button_sets:
#             faculty_button = InlineKeyboardButton(text=faculty_title, callback_data=faculty_key)
#             button_sets['faculties'].append(faculty_button)
#
#         if grade_key not in button_sets:
#             grade_button = InlineKeyboardButton(text=f'\t{emoji[grade]}\t', callback_data=grade_key)
#             button_sets[faculty_key].append(grade_button)
#
#         group_button = InlineKeyboardButton(text=title, callback_data=group_key)
#         button_sets[grade_key].append(group_button)
#
#     for key, button_set in button_sets.items():
#         new_keyboards[key] = build_keyboard(button_set)
#
#     return new_keyboards
# #
#
# def update_dynamic_keyboards():
#     global keyboards
#     global context_data_store
#     # Инициализация нового словаря контекста
#     context_data_store = {}
#
#     keyboards = get_group_keyboards()
#     keyboards.update(get_teacher_keyboards())
#     keyboards.update(static_keyboards)
#
#
# # Вспомогательная функция
# def generate_hash(data: dict) -> str:
#     """Генерирует хеш для данных контекста."""
#     data_string = json.dumps(data, sort_keys=True)
#     return hashlib.md5(data_string.encode()).hexdigest()
