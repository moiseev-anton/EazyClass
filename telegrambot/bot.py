import logging
import os
import time

import telebot
from django.core.cache import caches

from .keyboards import get_keyboard, context_data_store
from .services import CacheService, UserService, SubscriptionService
from .interface_messages import generate_home_answer

API_TOKEN = os.getenv('TELEGRAM_TOKEN')

bot = telebot.TeleBot(API_TOKEN)
cache = caches['telegrambot_cache']
logger = logging.getLogger(__name__)


# Обработчик команды /start
@bot.message_handler(commands=['start'])
def start_message(message):
    try:
        if UserService.sign_up_user(message.from_user):
            response_message = (f"Добро пожаловать!\n"
                                f"Выберите своё расписание для удобного доступа и получения уведомлений")
        else:
            response_message = ("С возвращением!")
        # Отправляем сообщение с клавиатурой
        bot.send_message(message.chat.id, response_message, reply_markup=get_keyboard('start'))
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
        user_data = CacheService.get_cached_user_data(telegram_id)
        if call.data == 'home':
            message, keyboard_key = generate_home_answer(user_data)
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text=message, reply_markup=get_keyboard(keyboard_key))
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

        elif call.data == 'teachers':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите преподавателя", reply_markup=get_keyboard(call.data))

        elif call.data.startswith('initial:'):
            _, initial = call.data.split(':')
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text="Выберите преподавателя", reply_markup=get_keyboard(call.data))

        elif call.data.startswith('context:'):
            context = context_data_store[call.data]
            user_data = CacheService.update_user_context(telegram_id, context)
            message = f'{context['title']}'
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                  text=message, reply_markup=get_keyboard('subscribe'))

        elif call.data == 'subscribe':
            context = user_data['context']
            model_name = context['model']
            obj_id = context.get('id')
            user_id = user_data['user_id']

            SubscriptionService.create_subscription(user_id, model_name, obj_id)
            CacheService.invalidate_user_cache(telegram_id)

            call.data = 'home'
            handle_callback_query(call)




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
                              text=error_message, reply_markup=get_keyboard('start'))


if __name__ == '__main__':
    while True:
        try:  # Запуск бота на ожидание сообщений
            bot.polling(True)
        # except requests.exceptions.ReadTimeout as e:
        except Exception as e:

            print("Ошибка подключения: ", e)
            print("Попытка переподключения через 5 секунд...")
            time.sleep(5)  # Пауза перед повторной попыткой подключения
