from celery import shared_task
from .keyboards import update_group_keyboard_cache, update_teacher_keyboard_cache


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def update_keyboard_cache():
    update_group_keyboard_cache()
    update_teacher_keyboard_cache()

# @shared_task
# def start_telegram_bot():
#     bot.polling(non_stop=True)
