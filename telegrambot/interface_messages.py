from .keyboards import home_teacher_keyboard, home_group_keyboard, short_home_keyboard


def generate_home_answer(user_data: dict):
    subscription = user_data['subscription']
    if not subscription:
        message = f'📌 расписание не выбрано'
        keyboard = short_home_keyboard
    elif subscription['type'] == 'teacher':
        message = f'📌 {subscription['name']}'
        keyboard = home_teacher_keyboard
    else:
        if user_data.subgroup != '0':
            message = (f'📌 {subscription['name']}\n'
                       f'подгруппа: {user_data.subgroup}')
        else:
            message = f'📌 {subscription['name']}'
        keyboard = home_group_keyboard

    return message, keyboard



