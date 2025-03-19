from aiogram import Router, types, F
from aiogram import html

from telegrambot.keyboards import KeyboardManager

router = Router()


@router.callback_query(F.data == "main")
async def main_handler(callback: types.CallbackQuery):
    await callback.message.edit_text(
        text=(f'👤 <b>{html.bold(callback.from_user.full_name)}</b>\n\n'
              f'⭐️ не выбрано'),
        reply_markup=KeyboardManager.main_group
    )
