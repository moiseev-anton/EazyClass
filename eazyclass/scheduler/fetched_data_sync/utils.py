import logging

import requests

logger = logging.getLogger(__name__)


def fetch_page_content(url: str) -> bytes:
    """Получает HTML страницу и возвращает её байтовое содержимое."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        logger.info(f"Успешно получен HTML: {url}")
        return response.content
    except requests.RequestException as e:
        logger.error(f"Ошибка запроса к {url}: {e}")
        raise
