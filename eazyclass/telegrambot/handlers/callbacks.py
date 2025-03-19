# Асинхронный обработчик нажатий на кнопки
def handle_callback_query(bot, call):
    try:
        chat_id = call.message.chat.id
        msg_id = call.message.message_id
        telegram_id = call.from_user.id
        user_data = User.objects.get_user_data_by_telegram_id(telegram_id)
        action, *params = call.data.split(':')
        if action == 'home':
            message, keyboard_key = generate_home_answer(user_data)
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                        text=message, reply_markup=get_keyboard(keyboard_key))
        # Выбор группы
        elif action == 'faculties':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                        text="Выберите направление", reply_markup=get_keyboard(call.data))

        elif action == 'faculty':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                        text="Выберите курс", reply_markup=get_keyboard(call.data))

        elif action == 'grade':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                        text="Выберите группу", reply_markup=get_keyboard(call.data))

        elif action == 'teachers':
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                        text="Выберите преподавателя", reply_markup=get_keyboard(call.data))

        elif action == 'initial':
            await bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                        text="Выберите преподавателя", reply_markup=get_keyboard(call.data))

        elif action == 'context':
            context = context_data_store[call.data]
            CacheService.update_user_context(telegram_id, context)
            message = f'{context['title']}'
            bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                        text=message, reply_markup=get_keyboard('subscribe'))

        elif action == 'subscribe':
            context = user_data['context']
            model_name = context['model']
            obj_id = context.get('id')
            user_id = user_data['user_id']

            SubscriptionService.create_subscription(user_id, model_name, obj_id)
            CacheService.invalidate_user_cache(telegram_id)

            call.data = 'home'
            handle_callback_query(call)

    except Exception as e:
        logger.error(f"Ошибка в обработке callback_query кнопки: {str(e)}")
        error_message = "Кажется что-то пошло не так. Попробуйте повторить позже"
        bot.edit_message_text(chat_id=chat_id, message_id=msg_id,
                                    text=error_message, reply_markup=get_keyboard('start'))