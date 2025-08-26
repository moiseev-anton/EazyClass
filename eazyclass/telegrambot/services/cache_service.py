import json
import logging
import os
from typing import Any, Optional, Dict
from pathlib import Path

from telegrambot.api_client import AsyncClientSession
from telegrambot.cache import CacheRepository

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(
        self,
        api_client: AsyncClientSession,
        faculties_cache_file: str,
        teachers_cache_file: str,
        cache_repository: CacheRepository,
    ):
        self.api_client = api_client
        self.faculties_cache_file = Path(faculties_cache_file)
        self.teachers_cache_file = Path(teachers_cache_file)
        self.cache_repository = cache_repository

    class DataFetchError(Exception):
        pass

    @staticmethod
    def load_from_file(file_path: Path) -> Optional[Dict[str, Any]]:
        """Загружает данные из файла или выбрасывает исключение."""
        try:
            if file_path.exists():
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
                    logger.warning(f"Invalid data format in {file_path}, expected dict")
            return None
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to load cache from {file_path}: {str(e)}")
            return None

    @staticmethod
    def save_to_file(file_path: Path, data: dict[str, Any]) -> bool:
        """Атомарно сохраняет данные в файл, возвращает статус успеха"""
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            temp_file = file_path.with_suffix('.tmp')

            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            temp_file.replace(file_path)
            logger.info(f"Data cached in {file_path}.")
            return True
        except (OSError, TypeError) as e:
            logger.error(f"Failed to save data to {file_path}: {str(e)}")
            return False

    async def _fetch_api_data(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """Получает данные из API или выбрасывает исключение."""
        try:
            response = await self.api_client.bot_request(endpoint=endpoint, method="GET")
            if isinstance(response, dict) and response.get("success", False):
                return response.get("data")
            logger.info(f"API returned error: {response.get('error', {})}")
            return None
        except Exception as e:
            logger.info(f"API request failed for {endpoint}: {str(e)}")
            return None

    async def update_data(self, endpoint: str, file_path: Path) -> Optional[dict[str, Any]]:
        """Основной метод обновления данных"""
        # Пробуем API
        api_data  = await self._fetch_api_data(endpoint)
        if isinstance(api_data , dict):
            self.save_to_file(file_path, api_data )
            return api_data

        # Пробуем файл
        file_data = self.load_from_file(file_path)
        if file_data is not None:
            logger.info(f"Using cached data from {file_path}")
            return file_data

        # Все источники недоступны
        logger.error(f"No valid data obtained for {endpoint}")
        return None

    async def update_faculties(self) -> bool:
        """Обновляет кэш факультетов при успешном получении данных"""
        data = await self.update_data("bot-faculties/", self.faculties_cache_file)
        if data is not None:
            self.cache_repository.faculties = data
            logger.info("Faculties cache updated successfully.")
            return True
        logger.warning("Faculties update failed, keeping existing data.")
        return False

    async def update_teachers(self) -> bool:
        """Обновляет кэш преподавателей при успешном получении данных"""
        data = await self.update_data("bot-teachers/", self.teachers_cache_file)
        if data is not None:
            self.cache_repository.teachers = data
            logger.info("Teachers cache updated successfully.")
            return True
        logger.warning("Teachers update failed, keeping existing data.")
        return False

    async def update_all(self) -> bool:
        """Обновляет все данные."""
        faculties_updated = await self.update_faculties()
        teachers_updated = await self.update_teachers()
        return faculties_updated and teachers_updated
