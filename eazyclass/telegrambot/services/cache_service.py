import asyncio
import json
import logging
import os
from typing import Any, Optional, Dict, Callable
from pathlib import Path


from telegrambot.api_client import AsyncClientSession
from telegrambot.cache import CacheRepository

logger = logging.getLogger(__name__)


class CacheService:
    class DataFetchError(Exception):
        pass

    def __init__(
        self,
        api_client: AsyncClientSession,
        cache_repository: CacheRepository,
        faculties_cache_file: str,
        teachers_cache_file: str,
    ):
        self.api_client = api_client
        self.cache_repository = cache_repository
        self.cache_files = {
            "faculties": Path(faculties_cache_file),
            "teachers": Path(teachers_cache_file),
        }

    @staticmethod
    def _load_from_file(file_path: Path) -> Optional[Dict[str, Any]]:
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
    def _save_to_file(file_path: Path, data: dict[str, Any]) -> bool:
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

    @staticmethod
    async def _build_faculties_dict(doc) -> dict:
        """Формирует словарь факультетов с группами, сгруппированными по курсам."""
        faculty_map = {
            f.id: {
                "id": int(f.id),
                "title": f.title,
                "short_title": f.shortTitle,
                "courses": {},
            }
            for f in doc.included if f.type == "faculty"
        }

        # Раскладываем группы по факультетам и курсам
        for group in doc.resources:
            await group.faculty.fetch()
            faculty_id = group.faculty.resource.id
            grade = group.grade
            faculty = faculty_map.setdefault(
                faculty_id,
                {"id": int(faculty_id), "title": "", "short_title": "", "courses": {}},
            )

            faculty["courses"].setdefault(grade, {})
            faculty["courses"][grade][group.id] = {
                "id": int(group.id),
                "title": group.title,
                "link": group.link,
            }

        return faculty_map

    @staticmethod
    async def _build_teachers_dict(doc) -> dict:
        """Формирует словарь преподавателей, сгруппированных по первой букве фамилии."""
        teachers: dict[str, Any] = {}

        for teacher in doc.resources:
            first_letter = teacher.full_name[0].upper()
            bucket = teachers.setdefault(first_letter, {})
            bucket[teacher.id] = {
                "id": int(teacher.id),
                "full_name": teacher.full_name,
                "short_name": teacher.short_name,
            }

        return teachers

    async def _fetch_data(
            self,
            file_path: Path,
            fetch_args: tuple,
            parser: Callable[[Any], dict]
    ) -> Optional[dict[str, Any]]:
        """Обновляет данные из API или файла.

        Сначала пытается получить данные из API, парсит их и сохраняет в файл.
        Если API недоступно, загружает данные из файла кеша.
        Если оба источника недоступны, возвращает None."""
        # Пробуем API
        try:
            doc = await self.api_client.get(*fetch_args)
            parsed = await parser(doc)
            if isinstance(parsed, dict):
                self._save_to_file(file_path, parsed)
                return parsed
            logger.warning(f"Parser returned invalid format for {file_path}")
        except Exception as e:
            logger.info(f"API request failed: {str(e)}")

        # Пробуем взять последний успешный вариант из файла
        file_data = self._load_from_file(file_path)
        if file_data is not None:
            logger.info(f"Using cached data from {file_path}")
            return file_data

        # Все источники недоступны
        logger.error(f"No valid data obtained for {file_path}")
        return None

    async def update_faculties(self) -> bool:
        """Обновляет кеш факультетов."""
        from jsonapi_client import Inclusion

        data = await self._fetch_data(
            file_path=self.cache_files["faculties"],
            fetch_args=("groups", Inclusion("faculty")),
            parser=self._build_faculties_dict,
        )
        if data is not None:
            self.cache_repository.faculties = data
            logger.info("Faculties cache updated successfully.")
            return True
        logger.warning("Faculties update failed, keeping existing data.")
        return False

    async def update_teachers(self) -> bool:
        """Обновляет кеш преподавателей."""
        data = await self._fetch_data(
            file_path=self.cache_files["teachers"],
            fetch_args=("teachers", ),
            parser=self._build_teachers_dict,
        )
        if data is not None:
            self.cache_repository.teachers = data
            logger.info("Teachers cache updated successfully.")
            return True
        logger.warning("Teachers update failed, keeping existing data.")
        return False

    async def update_all(self) -> bool:
        """Обновляет все кеши параллельно.
        True, если успешно обновлены все, иначе False."""
        results = await asyncio.gather(
            self.update_faculties(),
            self.update_teachers(),
            return_exceptions=True
        )
        return all(isinstance(r, bool) and r for r in results)
