from aiogram import types
from aiogram.fsm.context import FSMContext
from telegrambot.keyboards import KeyboardManager
from telegrambot.message_manager import MessageManager
import logging

logger = logging.getLogger(__name__)


async def handle_error(callback: types.CallbackQuery, state: FSMContext, message: str = None):
    """
    Универсальная функция для обработки ошибок.
    Отправляет стандартное сообщение об ошибке и сбрасывает состояние.
    """
    error_text = MessageManager.get_error_message()
    text = message if message else error_text

    await callback.message.edit_text(
        text,
        reply_markup=KeyboardManager.home
    )
    await callback.answer()

    await state.clear()
    logger.warning(f"Error handled: {text}")
