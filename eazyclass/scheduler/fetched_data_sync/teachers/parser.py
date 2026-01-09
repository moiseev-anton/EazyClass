import logging
from urllib.parse import urlencode

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def parse_teachers_page(html_content: bytes, page_path: str) -> dict[str, str]:
    """Парсит HTML и возвращает словарь (нормализованное имя учителя -> endpoint)."""
    soup = BeautifulSoup(html_content, "lxml")

    select = soup.find("select", attrs={"name": True})
    if not select:
        raise ValueError("На странице не найден <select> с преподавателями")

    param_name = select["name"]  # "idprep"
    teachers = {}

    for option in select.find_all("option"):
        if not option.get("value"):  # пропускаем disabled и placeholder
            continue

        teacher_id = option["value"]
        teacher_name = option.text.strip()
        endpoint = f"{page_path}?{urlencode({param_name: teacher_id})}"
        teachers[teacher_name] = endpoint

    return teachers
