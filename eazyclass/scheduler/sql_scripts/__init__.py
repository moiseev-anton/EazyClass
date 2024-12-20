from pathlib import Path

# Определяем путь к папке с текущим файлом (__init__.py)
SQL_SCRIPTS_DIR = Path(__file__).parent

# Указываем пути к файлам SQL-скриптов
CREATE_LESSON_TRIGGER_PATH = SQL_SCRIPTS_DIR / "create_lesson_trigger.sql"
DROP_LESSON_TRIGGER_PATH = SQL_SCRIPTS_DIR / "drop_lesson_trigger.sql"

# Словарь всех SQL-скриптов в этом пакете
SQL_FILES = {file.stem: file for file in SQL_SCRIPTS_DIR.glob("*.sql")}
