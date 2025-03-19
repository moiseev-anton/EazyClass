from telebot.types import Message
import logging
from scheduler.models import User
from telegrambot.interface_messages import MessageBuilder

logger = logging.getLogger(__name__)


# Асинхронный обработчик команды /start
def start_message(bot, message: Message):
    try:
        telegram_user = message.from_user
        user, created = User.objects.get_or_create_by_telegram(telegram_user)

        response_message = MessageBuilder.start_message(user, created)

        keyboard =

        bot.send_message(message.chat.id, response_message, reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Ошибка обработки команды start: {str(e)}")
        bot.send_message(message.chat.id, "Что-то пошло не так.\nПожалуйста, попробуйте позже.")


def handle_contact(bot, message: Message):
    try:
        UserService.update_contact(
            telegram_id=message.from_user.id,
            phone=message.contact.phone_number
        )
        bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=message.message_id,
            text="Номер сохранен ✅",
            reply_markup=get_keyboard('start')
        )
    except Exception as e:
        logger.error(f"Contact error: {e}")
        bot.send_message(message.chat.id, "Что-то пошло не так. Попробуйте позже.")
