import os
import time
from functools import lru_cache

import telebot
from eazyclass.scheduler.models import Faculty, Group
from django.core.cache import caches
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup
from .bot_utils import generate_faculty_keyboard, generate_group_keyboard, generate_course_keyboard

KEYBOARD_ROW_LENGTH = 4



API_TOKEN = os.getenv('TELEGRAM_TOKEN')

cache = caches['telegrambot_cache']
bot = telebot.TeleBot(API_TOKEN)

# today = datetime.now().strftime('%d.%m.%Y')
# tomorrow = (datetime.strptime(today, '%d.%m.%Y') + timedelta(days=1)).strftime('%d.%m.%Y')

# # Кеш группы, выбранной по умолчанию (с инвалидацией)
# user_group_cache = TTLCache(maxsize=100, ttl=3600)


def get_default_group(telegram_id):
    if telegram_id in user_group_cache.keys():
        return user_group_cache[telegram_id]
    else:
        group = get_user_group(telegram_id)
        if group:
            user_group_cache[telegram_id] = group
            return group



# Клавиатура home
button_home = InlineKeyboardButton(text='🏠 на главную', callback_data='actions')
home_keyboard = InlineKeyboardMarkup()
home_keyboard.add(button_home)

# Клавиатура actions (старая)
# button_faculty = InlineKeyboardButton(text='🎓 Выбрать группу', callback_data='faculty')
# button_set_group = InlineKeyboardButton(text='🎓 Выбрать группу', callback_data='faculty')
# actions_keyboard = InlineKeyboardMarkup()
# actions_keyboard.add(button_faculty)

# Клавиатура Выбрать группу
button_choice_group = InlineKeyboardButton(text='🎓 Выбрать группу', callback_data='faculty')
choice_keyboard = InlineKeyboardMarkup()
choice_keyboard.add(button_choice_group)

# Клавиатура actions
button_today = InlineKeyboardButton(text=f' На сегодня ', callback_data='today')
button_tomorrow = InlineKeyboardButton(text=f' На завтра ', callback_data='tomorrow')
button_week = InlineKeyboardButton(text=f' На неделю ', callback_data='week')
button_change_group = InlineKeyboardButton(text=f' Сменить группу', callback_data='faculty')

actions_keyboard = InlineKeyboardMarkup()
actions_keyboard.add(button_today)
actions_keyboard.add(button_tomorrow)
actions_keyboard.add(button_week)
actions_keyboard.add(button_change_group)


faculty_keyboard = generate_faculty_keyboard()


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_message(message):
    # Регистрация пользователя, запись в БД
    sing_up_user(message.from_user)
    def_group = get_default_group(message.chat.id)
    if def_group:
        bot.send_message(message.chat.id, f"Ваша группа: {def_group.title}",
                         reply_markup=actions_keyboard)
    else:
        bot.send_message(message.chat.id, "Привет! Этот бот поможет тебе ориентироваться в расписании занятий.",
                         reply_markup=choice_keyboard)


# Обработчик нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    try:
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        if call.data == 'actions':
            # tg_id = call.message.chat.id
            def_group = get_default_group(chat_id)
            if def_group:
                bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                      text=f" Ваша группа: {def_group.title} ", reply_markup=actions_keyboard)
            else:
                bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                      text=f" Выберите группу ", reply_markup=choice_keyboard)

        elif call.data == 'faculty':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите специальность", reply_markup=faculty_keyboard)

        elif call.data.startswith('f:'):
            _, fac = call.data.split(':')
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите курс", reply_markup=generate_course_keyboard(fac))

        elif call.data.startswith('c:'):
            _, course, fac = call.data.split(':')
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите группу", reply_markup=generate_group_keyboard(fac, course))

        elif call.data.startswith('g:'):
            _, group_id = call.data.split(':')
            set_default_group(chat_id, group_id)
            user_group_cache.pop(chat_id, None)
            def_group = get_default_group(chat_id)
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f" Ваша группа: {def_group.title}",
                                  parse_mode='HTML', reply_markup=actions_keyboard)

        # расписание новым сообщением
        elif call.data.startswith('today'):
            group = get_default_group(chat_id)
            link = group.link
            answer = get_schedule(link, today)
            bot.send_message(call.message.chat.id, answer, parse_mode='HTML', reply_markup=home_keyboard)
        elif call.data.startswith('tomorrow'):
            group = get_default_group(chat_id)
            link = group.link
            answer = get_schedule(link, tomorrow)
            bot.send_message(call.message.chat.id, answer, parse_mode='HTML', reply_markup=home_keyboard)

        # расписание с исправлением прошлого сообщения
        # elif call.data.startswith('today'):
        #     group = get_default_group(chat_id)
        #     link = group.link
        #     answer = get_schedule(link, today)
        #     bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        #                           text=answer, parse_mode='HTML', reply_markup=home_keyboard)

    except Exception as e:
        bot.send_message(call.message.chat.id, str(e), reply_markup=actions_keyboard)


if __name__ == '__main__':
    while True:
        try:  # Запуск бота на ожидание сообщений
            bot.polling(True)
        # except requests.exceptions.ReadTimeout as e:
        except Exception as e:

            print("Ошибка подключения: ", e)
            print("Попытка переподключения через 5 секунд...")
            time.sleep(5)  # Пауза перед повторной попыткой подключения
