def generate_home_answer(user_data: dict):
    subscriptions = user_data.get('subscriptions')
    if subscriptions:
        subscription = subscriptions[0]

        if user_data['subgroup'] != '0':
            message = (f'📌 {subscription['title']}\n'
                       f'подгруппа: {user_data.subgroup}')
        else:
            message = f'📌 {subscription['name']}'

        if subscriptions['model'] == 'Group':
            keyboard_key = 'home_group'
        else:
            keyboard_key = 'home_base'

    else:
        message = f'📌 расписание не выбрано'
        keyboard_key = 'home_short'

    return message, keyboard_key
