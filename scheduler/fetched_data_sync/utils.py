import logging
import re

import requests

logger = logging.getLogger(__name__)


def fetch_page_content(url: str) -> bytes:
    """Получает HTML страницу и возвращает её байтовое содержимое."""
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    logger.debug("Получена страница справочника",
                 extra={"event": "reference.page.received", "status_code": response.status_code})
    return response.content


def normalize_person_name(value: str) -> str:
    if not value:
        return ""

    value = value.lower()
    value = value.replace("ё", "е")
    value = re.sub(r"[^a-zа-яё]", "", value)

    return value
