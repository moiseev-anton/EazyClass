import asyncio
import logging
import sys

from aiogram import Dispatcher

from config import settings
from dependencies import Container
from telegrambot.handlers import start_router, main_router, faculty_router, teacher_router
from telegrambot.tasks import setup_periodic_task_scheduler

logging.basicConfig(level=getattr(logging, settings.log_level), stream=sys.stdout)
logger = logging.getLogger(__name__)


# Хуки запуска и остановки
async def on_startup(deps: Container):
    api_client = deps.api_client()
    cache_service = deps.cache_service()
    await api_client.start()
    await cache_service.update_all()  # Первичное обновление клавиатур
    await setup_periodic_task_scheduler(deps=deps)  # Запуск планировщика
    logger.info("Bot started.")


async def on_shutdown(deps: Container):
    api_client = deps.api_client()
    await api_client.close()
    logger.info("Bot stopped.")


async def main():
    container = Container()
    container.config.from_pydantic(settings)

    bot = container.bot()
    storage = container.storage()
    dp = Dispatcher(bot=bot, storage=storage, deps=container)

    dp.include_router(start_router)
    dp.include_router(main_router)
    dp.include_router(faculty_router)
    dp.include_router(teacher_router)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == '__main__':
    asyncio.run(main())



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
