import logging
import os
import time

import telebot
from django.core.cache import caches

from .keyboards import start_keyboard, get_keyboard
from .bot_utils import get_cached_user_data, sign_up_user
from .interface_messages import generate_home_answer

API_TOKEN = os.getenv('TELEGRAM_TOKEN')

bot = telebot.TeleBot(API_TOKEN)
cache = caches['telegrambot_cache']
logger = logging.getLogger(__name__)


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_message(message):
    try:
        if sign_up_user(message.from_user):
            response_message = (f"Добро пожаловать!\n"
                                f"Выберите своё расписание для удобного доступа и получения уведомлений")
        else:
            response_message = ("С возвращением!")
        # Отправляем сообщение с клавиатурой
        bot.send_message(message.chat.id, response_message, reply_markup=start_keyboard)
    except Exception as e:
        logger.error(f"Ошибка обработки команды start: {str(e)}")
        bot.send_message(message.chat.id, "Что-то пошло не так.\nПожалуйста, попробуйте позже.")


# Обработчик нажатий на кнопки
@bot.callback_query_handler(func=lambda call: True)
def handle_callback_query(call):
    try:
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        telegram_id = call.from_user.id
        user_data = get_cached_user_data(telegram_id)
        if call.data == 'home':
            message, keyboard = generate_home_answer(user_data)
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text=message, reply_markup=keyboard)
        # Выбор группы
        elif call.data == 'faculties':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите направление", reply_markup=get_keyboard(call.data))

        elif call.data.startswith('faculty:'):
            _, faculty = call.data.split(':')
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите курс", reply_markup=get_keyboard(call.data))

        elif call.data.startswith('grade:'):
            _, faculty, course = call.data.split(':')
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите группу", reply_markup=get_keyboard(call.data))

        elif call.data.startswith('group:'):
            _, group_id = call.data.split(':')
            # set_default_group(chat_id, group_id)
            # user_group_cache.pop(chat_id, None)
            # def_group = get_default_group(chat_id)
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text=f"Тут должна быть замена группы")

        # Выбор преподавателя
        elif call.data == 'teachers':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите преподавателя", reply_markup=get_keyboard(call.data))

        elif call.data.startswith('initial:'):
            _, initial = call.data.split(':')
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите преподавателя", reply_markup=get_keyboard(call.data))

        elif call.data.startswith('teacher:'):
            _, teacher_id = call.data.split(':')
            # TODO сделать расписание препода и кнопки Закрепить и Домой
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Тут должна быть замена препода")


        # расписание новым сообщением
        # elif call.data.startswith('today'):
        #     group = get_default_group(chat_id)
        #     link = group.link
        #     answer = get_schedule(link, today)
        #     bot.send_message(call.message.chat.id, answer, parse_mode='HTML', reply_markup=home_keyboard)
        # elif call.data.startswith('tomorrow'):
        #     group = get_default_group(chat_id)
        #     link = group.link
        #     answer = get_schedule(link, tomorrow)
        #     bot.send_message(call.message.chat.id, answer, parse_mode='HTML', reply_markup=home_keyboard)

        # расписание с исправлением прошлого сообщения
        # elif call.data.startswith('today'):
        #     group = get_default_group(chat_id)
        #     link = group.link
        #     answer = get_schedule(link, today)
        #     bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
        #                           text=answer, parse_mode='HTML', reply_markup=home_keyboard)

    except Exception as e:
        logger.error(f"Error processing callback_query : {str(e)}")
        error_message = "Кажется что-то пошло не так. Попробуйте повторить позже"
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text=error_message, reply_markup=start_keyboard)


if __name__ == '__main__':
    while True:
        try:  # Запуск бота на ожидание сообщений
            bot.polling(True)
        # except requests.exceptions.ReadTimeout as e:
        except Exception as e:

            print("Ошибка подключения: ", e)
            print("Попытка переподключения через 5 секунд...")
            time.sleep(5)  # Пауза перед повторной попыткой подключения
