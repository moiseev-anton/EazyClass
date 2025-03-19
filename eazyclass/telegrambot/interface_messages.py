from scheduler.models import User


class MessageBuilder:
    @staticmethod
    def start_message(user: User, is_new_user: bool) -> str:
        if is_new_user:
            return (f'Добро пожаловать, {user.first_name}! 👋\n\n'
                    f'Выберите свое расписание чтобы получать уведомления о изменениях')
        else:
            return f'C возвращением, {user.first_name}! 👋\n'

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
