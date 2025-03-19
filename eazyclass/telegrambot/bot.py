import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from dotenv import load_dotenv
from telegrambot.handlers import start_router, main_router

logger = logging.getLogger(__name__)

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../../.env"))

# bot = Bot(
#     token=settings.TELEGRAM_TOKEN,
#     default=DefaultBotProperties(parse_mode=ParseMode.HTML)
# )
#
# storage = RedisStorage.from_url(settings.TELEGRAM_REDIS_STORAGE_URL)
# dp = Dispatcher(storage=storage)


bot = Bot(
    token=os.getenv('TELEGRAM_BOT_TOKEN'),
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

storage = RedisStorage.from_url(os.getenv('TELEGRAM_REDIS_STORAGE_URL'))
dp = Dispatcher(storage=storage)

dp.include_router(start_router)
dp.include_router(main_router)


async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())

# # Асинхронный обработчик команды /start
# @bot.message_handler(commands=['start'])
# async def start_message(message):
#     try:
#         telegram_user = message.from_user
#         created = UserService.sign_up_user(telegram_user)
#         user_data = User.objects.get_user_data_by_telegram_id(telegram_user.id)
#
#         keyboard = get_keyboard('phone_request')
#         if created:
#             response_message = "Добро пожаловать!\nПожалуйста, поделитесь своим номером телефона"
#         elif user_data.get('phone_number'):
#             response_message = "С возвращением!"
#             keyboard = get_keyboard('start')
#         else:
#             response_message = "С возвращением!\nПожалуйста, поделитесь своим номером телефона"
#
#         # Асинхронная отправка сообщения с клавиатурой
#         await bot.send_message(message.chat.id, response_message, reply_markup=keyboard)
#     except Exception as e:
#         logger.error(f"Ошибка обработки команды start: {str(e)}")
#         await bot.send_message(message.chat.id, "Что-то пошло не так.\nПожалуйста, попробуйте позже.")
#
#
# @bot.message_handler(content_types=['contact'])
# async def handle_contact(message):
#     try:
#         chat_id = message.chat.id
#         msg_id = message.message_id
#         contact = message.contact
#         telegram_id = message.from_user.id
#
#         User.objects.update_contact(
#             telegram_id=telegram_id,
#             contact=contact
#         )
#
#         await bot.edit_message_text(chat_id=chat_id, message_id=msg_id, text="Номер сохранен",
#                                     reply_markup=get_keyboard('start'))
#
#     except Exception as e:
#         logger.error(f"Ошибка в обработке contact сообщения: {str(e)}")
#         error_message = "Кажется что-то пошло не так. Попробуйте повторить позже"
#         await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                     text=error_message, reply_markup=get_keyboard('start'))
#
#
# # Асинхронный обработчик нажатий на кнопки
# @bot.callback_query_handler(func=lambda call: True)
# async def handle_callback_query(call):
#     try:
#         chat_id = call.message.chat.id
#         msg_id = call.message.message_id
#         telegram_id = call.from_user.id
#         user_data = User.objects.get_user_data_by_telegram_id(telegram_id)
#         action, *params = call.data.split(':')
#         if action == 'home':
#             message, keyboard_key = generate_home_answer(user_data)
#             await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                         text=message, reply_markup=get_keyboard(keyboard_key))
#         # Выбор группы
#         elif action == 'faculties':
#             await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                         text="Выберите направление", reply_markup=get_keyboard(call.data))
#
#         elif action == 'faculty':
#             await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                         text="Выберите курс", reply_markup=get_keyboard(call.data))
#
#         elif action == 'grade':
#             await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                         text="Выберите группу", reply_markup=get_keyboard(call.data))
#
#         elif action == 'teachers':
#             await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                         text="Выберите преподавателя", reply_markup=get_keyboard(call.data))
#
#         elif action == 'initial':
#             await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                         text="Выберите преподавателя", reply_markup=get_keyboard(call.data))
#
#         elif action == 'context':
#             context = context_data_store[call.data]
#             CacheService.update_user_context(telegram_id, context)
#             message = f'{context['title']}'
#             await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                         text=message, reply_markup=get_keyboard('subscribe'))
#
#         elif action == 'subscribe':
#             context = user_data['context']
#             model_name = context['model']
#             obj_id = context.get('id')
#             user_id = user_data['user_id']
#
#             SubscriptionService.create_subscription(user_id, model_name, obj_id)
#             CacheService.invalidate_user_cache(telegram_id)
#
#             call.data = 'home'
#             await handle_callback_query(call)
#
#     except Exception as e:
#         logger.error(f"Ошибка в обработке callback_query кнопки: {str(e)}")
#         error_message = "Кажется что-то пошло не так. Попробуйте повторить позже"
#         await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
#                                     text=error_message, reply_markup=get_keyboard('start'))
