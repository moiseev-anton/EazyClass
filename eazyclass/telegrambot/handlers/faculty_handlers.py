import logging

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from telegrambot.dependencies import Container
from telegrambot.managers.keyboard_manager import (
    FacultyCallback,
    CourseCallback,
    GroupCallback,
)
from telegrambot.states import FacultyStates

logger = logging.getLogger(__name__)


router = Router()


@router.callback_query(F.data == "faculties")
async def faculties_handler(
    callback: types.CallbackQuery, state: FSMContext, deps: Container
):
    await callback.message.edit_text(
        text=deps.message_manager().get_faculties_message(),
        reply_markup=deps.keyboard_manager().get_faculties_keyboard(),
    )
    await state.set_state(FacultyStates.selecting_faculty)
    await callback.answer()


@router.callback_query(FacultyCallback.filter())
async def faculty_courses_handler(
    callback: types.CallbackQuery,
    callback_data: FacultyCallback,
    state: FSMContext,
    deps: Container,
):
    faculty_id = callback_data.key
    await state.update_data(faculty_id=faculty_id)
    await callback.message.edit_text(
        text=deps.message_manager().get_courses_message(faculty_id),
        reply_markup=deps.keyboard_manager().get_courses_keyboard(faculty_id),
    )
    await state.set_state(FacultyStates.selecting_course)
    await callback.answer()


@router.callback_query(CourseCallback.filter())
async def course_groups_handler(
    callback: types.CallbackQuery,
    callback_data: CourseCallback,
    state: FSMContext,
    deps: Container,
):
    course_id = callback_data.key
    data = await state.get_data()
    faculty_id = data.get("faculty_id")
    await state.update_data(course_id=course_id)
    await callback.message.edit_text(
        text=deps.message_manager().get_groups_message(faculty_id, course_id),
        reply_markup=deps.keyboard_manager().get_groups_keyboard(faculty_id, course_id),
    )
    await state.set_state(FacultyStates.selecting_group)
    await callback.answer()


@router.callback_query(GroupCallback.filter())
async def group_selected_handler(
    callback: types.CallbackQuery,
    callback_data: GroupCallback,
    state: FSMContext,
    deps: Container,
):
    group_id = callback_data.id
    await state.update_data(group_id=group_id)
    data = await state.get_data()
    faculty_id = data.get("faculty_id")
    course_id = data.get("course_id")
    group_data = deps.cache_repository().get_group(faculty_id, course_id, group_id)

    await callback.message.edit_text(
        text=deps.message_manager().get_group_selected_message(group_data),
        reply_markup=deps.keyboard_manager().get_actions_keyboard("group", group_data),
    )
    await state.set_state(FacultyStates.selecting_action)
    await callback.answer()
