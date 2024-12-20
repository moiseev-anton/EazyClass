import os
from django.db import connection
from scheduler.sql_scripts import CREATE_LESSON_TRIGGER_PATH, DROP_LESSON_TRIGGER_PATH

TRIGGER_SCRIPTS = {
    'create': CREATE_LESSON_TRIGGER_PATH,
    'drop': DROP_LESSON_TRIGGER_PATH
}


def execute_trigger_action(action: str):
    """
    Выполняет действие для управления триггером изменения расписания (создание или удаление).
    """
    if action not in TRIGGER_SCRIPTS:
        raise ValueError(f"Недопустимое действие: {action}. Доступные действия: {list(TRIGGER_SCRIPTS.keys())}")

    script_path = TRIGGER_SCRIPTS[action]

    if not os.path.exists(script_path):
        raise FileNotFoundError(f"Файл скрипта {script_path} не найден.")

    with open(script_path, 'r') as sql_file:
        sql_script = sql_file.read()

    with connection.cursor() as cursor:
        cursor.execute(sql_script)

    return f"Действие {action} выполнено успешно."
