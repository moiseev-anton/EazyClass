from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from telegrambot.keyboards import KeyboardManager, FacultyCallback, CourseCallback, GroupCallback
from telegrambot.message_manager import MessageManager
from telegrambot.states import FacultyStates
from telegrambot.handlers.error_handler import handle_error
import logging

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "faculties")
async def faculties_handler(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        text=MessageManager.get_faculties_message(),
        reply_markup=KeyboardManager.get_faculties_keyboard()
    )
    await state.set_state(FacultyStates.selecting_faculty)
    await callback.answer()


@router.callback_query(FacultyCallback.filter())
async def faculty_courses_handler(callback: types.CallbackQuery, callback_data: FacultyCallback, state: FSMContext):
    faculty_id = callback_data.key
    await state.update_data(faculty_id=faculty_id)
    await callback.message.edit_text(
        text=MessageManager.get_courses_message(faculty_id),
        reply_markup=KeyboardManager.get_courses_keyboard(faculty_id),
    )
    await state.set_state(FacultyStates.selecting_course)
    await callback.answer()


@router.callback_query(CourseCallback.filter())
async def course_groups_handler(callback: types.CallbackQuery, callback_data: CourseCallback, state: FSMContext):
    course_id = callback_data.key
    data = await state.get_data()
    faculty_id = data.get("faculty_id")
    # if not faculty_id:
    #     await handle_error(callback, state)
    #     return
    await state.update_data(course_id=course_id)
    await callback.message.edit_text(
        text=MessageManager.get_groups_message(faculty_id, course_id),
        reply_markup=KeyboardManager.get_groups_keyboard(faculty_id, course_id),
    )
    await state.set_state(FacultyStates.selecting_group)
    await callback.answer()


@router.callback_query(GroupCallback.filter())
async def group_selected_handler(callback: types.CallbackQuery, callback_data: GroupCallback, state: FSMContext):
    group_id = callback_data.id
    data = await state.get_data()
    faculty_id = data.get("faculty_id")
    course_id = data.get("course_id")
    # if not faculty_id or not course_id:
    #     await handle_error(callback, state)
    #     return
    await callback.message.edit_text(
        text=MessageManager.get_group_selected_message(faculty_id, course_id, group_id),
        reply_markup=KeyboardManager.home,
    )
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == "back")
async def back_handler(callback: types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    data = await state.get_data()
    faculty_id = data.get("faculty_id")

    if current_state == FacultyStates.selecting_course.state:
        await faculties_handler(callback, state)
    elif current_state == FacultyStates.selecting_group.state and faculty_id:
        if faculty_id:
            fake_callback_data = FacultyCallback(key=faculty_id)
            await faculty_courses_handler(callback, fake_callback_data, state)
    else:
        await handle_error(callback, state)




