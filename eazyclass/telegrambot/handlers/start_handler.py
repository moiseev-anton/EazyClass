import logging

from aiogram import Router, types
from aiogram.filters import CommandStart, CommandObject

from telegrambot.dependencies import Container

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
@router.message(CommandStart(deep_link=True))
async def start_handler(
    message: types.Message, command: CommandObject, deps: Container
):
    # Собираем данные пользователя из Telegram
    tlg_user = message.from_user
    nonce = command.args

    try:
        response = await deps.user_service(user=tlg_user).register_or_login_user(nonce)

        # Формируем ответ пользовател
        reply = deps.message_manager().get_start_message(
            user=response["user"],
            created=response["created"],
            nonce_status=response.get("nonce_status"),
        )

        await message.answer(text=reply, reply_markup=deps.keyboard_manager().home)
    except Exception as e:
        logger.error(f"Error processing /start: {str(e)}")
        await message.answer("Произошла ошибка. Попробуйте позже.")
