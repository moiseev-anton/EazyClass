import re

from pydantic import BaseModel, field_validator


class GroupData(BaseModel):
    title: str
    endpoint: str

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, v: str) -> str:
        return v.strip()

    @property
    def course(self) -> int | None:
        s = self.title.lstrip(" 0")
        match = re.match(r"(\d+)", s)
        if not match:
            return None
        return int(match.group(1)[0])


class FacultyData(BaseModel):
    title: str
    groups: list[GroupData]

    @property
    def short_title(self) -> str:
        if not self.groups:
            return self.make_short_title_from_faculty_name(self.title)
        return self.extract_short_faculty_title([g.title for g in self.groups])

    def model_dump(self, **kwargs):
        data = super().model_dump(**kwargs)
        data["short_title"] = self.short_title
        return data

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, v: str) -> str:
        v = v.strip()
        cleaned = re.sub(r"^[^А-ЯA-Zа-яa-z]+", "", v)
        cleaned = re.sub(r"\s+", " ", cleaned)
        # cleaned = re.sub(r"\(.*?\)", "", cleaned)  # удаление скобок с содержимым (...)
        return cleaned if cleaned else v.strip()

    @staticmethod
    def extract_short_faculty_title(group_titles: list[str]) -> str:
        """
        Формирует краткое название факультета по общему префиксу названий групп.
        Пример: ["11 ИСиП-В", "12 ИСиП-П", "13 ИСиП-ДОП"] → "ИСиП"
        """
        if not group_titles:
            return ""

        # Убираем ведущие небуквенные символы перед аббревиатурой
        cleaned = [re.sub(r"^[^a-zA-Zа-яА-ЯёЁ]+", "", title) for title in group_titles]
        # Берем первый как базу
        result = cleaned[0]
        for title in cleaned[1:]:
            # Ищем общие символы с начала
            prefix = "".join(t1 if t1.upper() == t2.upper() else "" for t1, t2 in zip(result, title))
            result = re.sub(r"[^a-zA-Zа-яА-ЯёЁ]+$", "", prefix)
        # обрезаем лишнее
        return result.strip()

    @staticmethod
    def make_short_title_from_faculty_name(faculty_name: str) -> str:
        """
        Формирует краткое название факультета по первым буквам каждого слова.
        Всё, что в скобках (), удаляется.

        Пример:
          "Мехатроника и мобильная робототехника (по отраслям)" → "МиМР"
          "Информационные системы и программирование" → "ИСиП"
        """
        if not faculty_name:
            return ""

        # Убираем содержимое в скобках
        cleaned = re.sub(r"\(.*?\)", "", faculty_name).strip()
        # Разбиваем на слова по пробелам и оставляем только слова с буквами
        words = [w for w in cleaned.split() if re.search(r"[а-яА-ЯёЁa-zA-Z]", w)]

        short_title_chars = []
        for w in words:
            first_char = w[0]
            if first_char.lower() == "и" and len(w) == 1:
                short_title_chars.append("и")
            else:
                short_title_chars.append(first_char.upper())

        return "".join(short_title_chars)
