import logging

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from telegrambot.dependencies import Container
from telegrambot.handlers.error_handler import handle_error
from telegrambot.managers.keyboard_manager import AlphabetCallback, TeacherCallback
from telegrambot.states import TeacherStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "alphabet")
async def alphabet_handler(
    callback: types.CallbackQuery, state: FSMContext, deps: Container
):
    await callback.message.edit_text(
        text=deps.message_manager().get_alphabet_message(),
        reply_markup=deps.keyboard_manager().get_alphabet_keyboard(),
    )
    await state.set_state(TeacherStates.selecting_letter)
    await callback.answer()


@router.callback_query(AlphabetCallback.filter())
async def teachers_handler(
    callback: types.CallbackQuery,
    callback_data: AlphabetCallback,
    state: FSMContext,
    deps: Container,
):
    letter = callback_data.letter
    await state.update_data(letter=letter)
    await callback.message.edit_text(
        text=deps.message_manager().get_teachers_message(letter),
        reply_markup=deps.keyboard_manager().get_teachers_keyboard(letter),
    )
    await state.set_state(TeacherStates.selecting_teacher)
    await callback.answer()


@router.callback_query(TeacherCallback.filter())
async def teacher_selected_handler(
    callback: types.CallbackQuery,
    callback_data: TeacherCallback,
    state: FSMContext,
    deps: Container,
):
    teacher_id = callback_data.id
    await state.update_data(teacher_id=teacher_id)
    data = await state.get_data()
    letter = data.get("letter")
    teacher_data = deps.cache_repository().get_teacher(letter, teacher_id)
    await callback.message.edit_text(
        text=deps.message_manager().get_teacher_selected_message(teacher_data),
        reply_markup=deps.keyboard_manager().get_actions_keyboard("teacher", teacher_data),
    )
    await state.set_state(TeacherStates.selecting_action)
    await callback.answer()
