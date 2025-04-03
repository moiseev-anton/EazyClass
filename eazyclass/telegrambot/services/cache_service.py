import json
import logging
import os
from typing import Any

from telegrambot.api_client import ApiClient
from telegrambot.cache import cache_manager

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self, api_client: ApiClient, faculties_cache_file: str, teachers_cache_file: str):
        self.api_client = api_client
        self.faculties_cache_file = faculties_cache_file
        self.teachers_cache_file = teachers_cache_file

    @staticmethod
    def load_from_file(file_path: str) -> dict[str, Any]:
        """Загружает данные из файла"""
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    @staticmethod
    def save_to_file(file_path: str, data: dict[str, Any]) -> None:
        """Сохраняет данные в файл."""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)  # Создаём директорию, если её нет
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Data cached in {file_path}.")

    async def update_data(self, endpoint: str, file_path: str) -> dict:
        """
        Обновляет данные с использованием API или файла.
        Возвращает обновлённые данные.
        """
        # Пробуем загрузить API
        try:
            data = await self.api_client.bot_request(endpoint=endpoint, method="GET")
            if not isinstance(data, dict):
                logger.warning(f"Invalid data format from API ({endpoint}), falling back to file.")
                raise ValueError("Invalid API data format")
            self.save_to_file(file_path, data)
            return data
        except Exception as e:
            logger.info(f"Falling back to file due to API error: {str(e)}")

        # Если API не сработал, пробуем из файла
        try:
            data = self.load_from_file(file_path)
            if not data:
                logger.info(f"No data in file ({file_path}), returning empty dict.")
            else:
                logger.info(f"Data loaded from file ({file_path}) as fallback.")
            return data
        except Exception as e:
            logger.error(f"Failed to load keyboard data from file ({file_path}): {str(e)}")
            return {}

    async def update_faculties(self) -> dict[str, Any]:
        """Обновляет кэш факультетов и сохраняет в указанный файл."""
        faculties_data = await self.update_data('bot-faculties/', self.faculties_cache_file)
        cache_manager.faculties = faculties_data
        return faculties_data

    async def update_teachers(self) -> dict[str, Any]:
        """Обновляет кэш преподавателей и сохраняет в указанный файл."""
        teachers_data = await self.update_data('bot-teachers/', self.teachers_cache_file)
        cache_manager.teachers = teachers_data
        return teachers_data

    async def update_all(self) -> None:
        await self.update_faculties()
        logger.info("Faculties updated.")
        await self.update_teachers()
        logger.info("Teachers updated.")
