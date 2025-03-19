from aiogram import Router, types
from aiogram import html
from aiogram.filters import Command

from telegrambot.keyboards import KeyboardManager

router = Router()


@router.message(Command("start"))
async def start_handler(message: types.Message):
    await message.answer(
        text=(f'<b>Добро пожаловать, {html.bold(message.from_user.full_name)}!</b> 👋\n\n'
              f'Выберите свое расписание чтобы получать уведомления о изменениях'),
        reply_markup=KeyboardManager.home
    )
