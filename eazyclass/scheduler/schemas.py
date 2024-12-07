from datetime import date, datetime
from typing import Any

from annotated_types import MaxLen
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Annotated

from scheduler.models import Subject, Classroom, Teacher

MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field('title').max_length
MAX_CLASSROOM_TITLE_LENGTH = Classroom._meta.get_field('title').max_length
MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field('full_name').max_length
SUBJECT_DEFAULT_VALUE = 'Не указано'
TEACHER_DEFAULT_VALUE = 'Не указано'
CLASSROOM_DEFAULT_VALUE = '(дист)'
SUBGROUP_DEFAULT_VALUE = 0


class LessonParser(BaseModel):
    """
    Схема для парсинга данных об уроках

    Attributes:
        lesson_number (int): Номер урока (от 1 до 9). Обязательное поле.
        subject_title (str): Название предмета. По умолчанию 'Не указано'.
        classroom_title (str): Название аудитории. По умолчанию '(дист)'.
        teacher_fullname (str): ФИО преподавателя. По умолчанию 'Не указано'.
        subgroup (int): Подгруппа (0 или от 1 до 9). По умолчанию 0.
        date (date): Дата проведения урока. По умолчанию None.
        group_id (int): ID группы. По умолчанию None.
    """
    lesson_number: int = Field(..., ge=1, le=9, description="Номер урока (от 1 до 9)")
    subject_title: str = Field(default=SUBJECT_DEFAULT_VALUE,
                               max_length=MAX_SUBJECT_TITLE_LENGTH,
                               description="Название предмета")
    classroom_title: str = Field(default=CLASSROOM_DEFAULT_VALUE,
                                 max_length=MAX_CLASSROOM_TITLE_LENGTH,
                                 description="Название аудитории")
    teacher_fullname: str = Field(default=TEACHER_DEFAULT_VALUE,
                                  max_length=MAX_TEACHER_FULLNAME_LENGTH,
                                  description="ФИО преподавателя")
    subgroup: int = Field(default=SUBGROUP_DEFAULT_VALUE, ge=0, le=9, description="Подгруппа (0 или от 1 до 9)")
    date: Annotated[date, Field(default=None, description="Дата проведения урока")]
    group_id: int = Field(default=None, ge=0, description="ID группы")

    @field_validator("date", mode='before')
    @classmethod
    def parse_date(cls, value: Any) -> date:
        """
        Валидатор для обработки поля `date`.

        Args:
            value (Any): Значение, переданное в поле `date`.

        Returns:
            date: Объект `date`, если значение валидно.

        Raises:
            ValueError: Если формат даты некорректен.
        """
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            formats = ['%d.%m.%Y', '%Y-%m-%d']  # Поддерживаемые форматы даты
            for fmt in formats:
                try:
                    return datetime.strptime(value.strip(), fmt).date()
                except ValueError:
                    continue
            raise ValueError(f"Некорректный формат даты: '{value}'. Ожидается один из форматов: {formats}")

    @field_validator("subject_title", 'classroom_title', 'teacher_fullname', mode='before')
    @classmethod
    def truncate_string(cls, value: Any, info) -> str:
        """
        Валидатор для обрезки строковых значений полей содержащих max_length.

        Args:
            value (Any): Значение, переданное в поле.
            info: Информация о поле.

        Returns:
            str: Обрезанная строка.
        """
        if isinstance(value, str):
            # Ищем объект MaxLen в metadata чтобы получить max_length поля
            for meta in cls.model_fields[info.field_name].metadata:
                if isinstance(meta, MaxLen):
                    max_length = meta.max_length
                    if len(value) > max_length:
                        value = value[:max_length]  # Обрезаем строку до max_length
        return value

    @model_validator(mode="before")
    @classmethod
    def replace_empty_with_default(cls, values: dict[str, Any]) -> dict[str, Any]:
        """
        Валидатор для замены пустых строк значениями по умолчанию

        Args:
            values (dict[str, Any]): Словарь входных данных.

        Returns:
            dict[str, Any]: Обновленный словарь данных.
        """
        for field_name, value in values.items():
            if isinstance(value, str):
                stripped_value = value.strip()
                if stripped_value == "":
                    default_value = cls.model_fields[field_name].default
                    values[field_name] = default_value
                else:
                    values[field_name] = stripped_value
        return values
