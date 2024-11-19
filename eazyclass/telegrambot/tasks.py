from celery import shared_task
from .keyboards import update_dynamic_keyboards


@shared_task(bind=True, max_retries=3, default_retry_delay=60, queue='periodic_tasks')
def update_keyboards():
    update_dynamic_keyboards()

