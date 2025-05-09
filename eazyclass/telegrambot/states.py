from aiogram.fsm.state import State, StatesGroup


class FacultyStates(StatesGroup):
    selecting_faculty = State()
    selecting_course = State()
    selecting_group = State()
    selecting_action = State()
    action = State()


class TeacherStates(StatesGroup):
    selecting_letter = State()
    selecting_teacher = State()
    selecting_action = State()
    action = State()
