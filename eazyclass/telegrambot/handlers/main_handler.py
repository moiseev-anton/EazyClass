from aiogram import Router, types, F
from aiogram import html
from aiogram.fsm.context import FSMContext

from telegrambot.dependencies import Container

router = Router()


@router.callback_query(F.data == "main")
async def main_handler(callback: types.CallbackQuery, state: FSMContext, deps: Container):
    await callback.message.edit_text(
        text=(
            f"👤 <b>{html.bold(callback.from_user.full_name)}</b>\n\n" f"⭐️ не выбрано"
        ),
        reply_markup=deps.keyboard_manager().main_group,
    )
    await state.clear()
    await callback.answer()
