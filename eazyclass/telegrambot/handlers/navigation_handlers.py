import logging

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from telegrambot.dependencies import Container
from telegrambot.handlers.error_handler import handle_error
from telegrambot.handlers.faculty_handlers import (
    faculties_handler,
    faculty_courses_handler,
    course_groups_handler,
    FacultyCallback,
    CourseCallback, group_selected_handler
)
from telegrambot.handlers.teacher_handlers import (alphabet_handler,
                                                   teachers_handler,
                                                   AlphabetCallback, teacher_selected_handler
                                                   )
from telegrambot.managers.keyboard_manager import GroupCallback, TeacherCallback
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
    match current_state:
        case FacultyStates.selecting_course.state:
            await faculties_handler(callback, state, deps)
            return
        case FacultyStates.selecting_group.state:
            faculty_id = data.get("faculty_id")
            fake_callback_data = FacultyCallback(key=faculty_id)
            await faculty_courses_handler(callback, fake_callback_data, state, deps)
            return
        case FacultyStates.selecting_action.state:
            course = data.get("course_id")
            fake_callback_data = CourseCallback(key=course)
            await course_groups_handler(callback, fake_callback_data, state, deps)
            return
        case FacultyStates.action.state:
            group_id = data.get("group_id")
            fake_callback_data = GroupCallback(id=group_id)
            await group_selected_handler(callback, fake_callback_data, state, deps)
            return

        case TeacherStates.selecting_teacher.state:
            await alphabet_handler(callback, state, deps)
            return
        case TeacherStates.selecting_action.state:
            letter = data.get("letter")
            fake_callback_data = AlphabetCallback(letter=letter)
            await teachers_handler(callback, fake_callback_data, state, deps)
            return
        case TeacherStates.action.state:
            teacher_id = data.get("teacher_id")
            fake_callback_data = TeacherCallback(id=teacher_id)
            await teacher_selected_handler(callback, fake_callback_data, state, deps)
            return

        case _:
            await handle_error(callback, state)

