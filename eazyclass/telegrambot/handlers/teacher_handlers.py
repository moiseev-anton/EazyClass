from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from telegrambot.keyboards import KeyboardManager, AlphabetCallback, TeacherCallback
from telegrambot.states import TeacherStates
from telegrambot.message_manager import MessageManager
from telegrambot.handlers.error_handler import handle_error
import logging

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "alphabet")
async def alphabet_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text=MessageManager.get_alphabet_message(),
        reply_markup=KeyboardManager.get_alphabet_keyboard(),
    )
    await state.set_state(TeacherStates.selecting_letter)
    await callback.answer()


@router.callback_query(AlphabetCallback.filter())
async def teachers_handler(callback: types.CallbackQuery, callback_data: AlphabetCallback, state: FSMContext):
    letter = callback_data.letter
    await state.update_data(letter=letter)
    await callback.message.edit_text(
        text=MessageManager.get_teachers_message(letter),
        reply_markup=KeyboardManager.get_teachers_keyboard(letter),
    )
    await state.set_state(TeacherStates.selecting_teacher)
    await callback.answer()


@router.callback_query(TeacherCallback.filter())
async def teacher_selected_handler(callback: types.CallbackQuery, callback_data: TeacherCallback, state: FSMContext):
    teacher_id = callback_data.id
    data = await state.get_data()
    letter = data.get("letter")
    if not letter:
        await handle_error(callback, state)
        return
    await callback.message.edit_text(
        text=MessageManager.get_teacher_selected_message(letter, teacher_id),
        reply_markup=KeyboardManager.home,
    )
    await state.clear()
    await callback.answer()
