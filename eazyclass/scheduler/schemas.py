from datetime import date, datetime

from annotated_types import MaxLen
from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Annotated

from scheduler.models import Subject, Classroom, Teacher

# MAX_SUBJECT_TITLE_LENGTH = 255
# MAX_CLASSROOM_TITLE_LENGTH = 10
# MAX_TEACHER_FULLNAME_LENGTH = 64
MAX_SUBJECT_TITLE_LENGTH = Subject._meta.get_field('title').max_length
MAX_CLASSROOM_TITLE_LENGTH = Classroom._meta.get_field('title').max_length
MAX_TEACHER_FULLNAME_LENGTH = Teacher._meta.get_field('full_name').max_length
SUBJECT_DEFAULT_VALUE = 'Не указано'
TEACHER_DEFAULT_VALUE = 'Не указано'
CLASSROOM_DEFAULT_VALUE = '(дист)'
SUBGROUP_DEFAULT_VALUE = 0


class LessonParser(BaseModel):
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
    def parse_date(cls, value):
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
    def truncate_string(cls, value, info):
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
    def replace_empty_with_default(cls, values):
        for field_name, value in values.items():
            if isinstance(value, str):
                stripped_value = value.strip()
                if stripped_value == "":
                    default_value = cls.model_fields[field_name].default
                    values[field_name] = default_value
                else:
                    values[field_name] = stripped_value
        return values
