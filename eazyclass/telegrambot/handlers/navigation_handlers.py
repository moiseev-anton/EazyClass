import logging

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from telegrambot.dependencies import Container
from telegrambot.handlers.error_handler import handle_error
from telegrambot.handlers.faculty_handlers import (
    faculties_handler,
    faculty_courses_handler,
    FacultyCallback,
)
from telegrambot.handlers.teacher_handlers import alphabet_handler
from telegrambot.states import FacultyStates, TeacherStates

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "back")
async def back_handler(
    callback: types.CallbackQuery, state: FSMContext, deps: Container
):
    current_state = await state.get_state()
    data = await state.get_data()

    # Навигация по факультетам
    if current_state == FacultyStates.selecting_course.state:
        await faculties_handler(callback, state, deps)
        return
    elif current_state == FacultyStates.selecting_group.state:
        faculty_id = data.get("faculty_id")
        if faculty_id:
            fake_callback_data = FacultyCallback(key=faculty_id)
            await faculty_courses_handler(callback, fake_callback_data, state, deps)
            return

    # Навигация по учителям
    elif current_state == TeacherStates.selecting_teacher.state:
        letter = data.get("letter")
        if letter:
            await alphabet_handler(callback, state, deps)
            return

    # Неизвестное состояние
    await handle_error(callback, state)
