from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from telegrambot.dependencies import Container
from telegrambot.managers.keyboard_manager import ActionCallback
from telegrambot.states import TeacherStates, FacultyStates

router = Router()


@router.callback_query(ActionCallback.filter((F.action == "schedule") & (F.obj_type == "group")))
async def group_schedule_action_handler(callback: types.CallbackQuery, callback_data: ActionCallback, state: FSMContext, deps: Container):
    obj_type = callback_data.obj_type
    group_id = callback_data.id
    user = callback.from_user

    data = await state.get_data()
    faculty_id = data.get("faculty_id")
    course_id = data.get("course_id")
    group_data = deps.cache_repository().get_group(faculty_id, course_id, group_id)

    lessons_data = await deps.lesson_service(user=user).get_actual_lessons(obj_type, group_id)
    text = deps.message_manager().format_group_schedule(group_title=group_data.get("title"), schedule_data=lessons_data)

    await callback.message.edit_text(
        text=text,
        reply_markup=deps.keyboard_manager().back_home,
    )
    await state.set_state(FacultyStates.action)
    await callback.answer()


@router.callback_query(ActionCallback.filter((F.action == "schedule") & (F.obj_type == "teacher")))
async def teacher_schedule_action_handler(
    callback: types.CallbackQuery,
    callback_data: ActionCallback,
    state: FSMContext,
    deps: Container,
):
    obj_type = callback_data.obj_type
    teacher_id = callback_data.id
    user = callback.from_user

    data = await state.get_data()
    letter = data.get("letter")
    teacher_data = deps.cache_repository().get_teacher(letter, teacher_id)

    lessons_data = await deps.lesson_service(user=user).get_actual_lessons(obj_type, teacher_id)
    text = deps.message_manager().format_teacher_schedule(teacher_data.get('short_name'), lessons_data)

    await callback.message.edit_text(
        text=text,
        reply_markup=deps.keyboard_manager().back_home
    )
    await state.set_state(TeacherStates.action)
    await callback.answer()
