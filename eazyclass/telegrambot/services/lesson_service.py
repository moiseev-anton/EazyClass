import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional, Dict, Any

from aiogram.types import User

from telegrambot.api_client import AsyncClientSession

logger = logging.getLogger(__name__)


@dataclass
class DateRange:
    date_from: Optional[date] = None
    date_to: Optional[date] = None


class LessonService:
    def __init__(self, api_client: AsyncClientSession, user: User):
        self.api_client = api_client
        self.user = user

    # Основные методы для конкретного объекта
    async def get_actual_lessons(self, obj_type: str, obj_id: str) -> Dict[str, Any]:
        """Получает актуальные уроки (начиная с сегодня)"""
        return await self._get_lessons_with_range(obj_type, obj_id, DateRange(date_from=date.today()))

    async def get_today_lessons(self, obj_type: str, obj_id: str) -> Dict[str, Any]:
        """Получает уроки только на сегодня"""
        today = date.today()
        return await self._get_lessons_with_range(obj_type, obj_id, DateRange(today, today))

    async def get_tomorrow_lessons(self, obj_type: str, obj_id: str) -> Dict[str, Any]:
        """Получает уроки только на завтра"""
        tomorrow = date.today() + timedelta(days=1)
        return await self._get_lessons_with_range(obj_type, obj_id, DateRange(tomorrow, tomorrow))

    async def get_current_week_lessons(self, obj_type: str, obj_id: str) -> Dict[str, Any]:
        """Получает уроки на текущую неделю"""
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        return await self._get_lessons_with_range(obj_type, obj_id, DateRange(start_of_week, end_of_week))

    async def get_lessons(
            self,
            obj_type: str,
            obj_id: str,
            date_from: Optional[date] = None,
            date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Основной метод для получения уроков с фильтрацией по датам"""
        return await self._get_lessons_with_range(obj_type, obj_id, DateRange(date_from, date_to))

    # Методы для работы с подпиской пользователя (/lessons/me/)
    async def get_actual_lessons_for_subscription(self) -> Dict[str, Any]:
        """Актуальные уроки (с сегодня) для текущей подписки"""
        return await self._get_subscription_lessons(DateRange(date_from=date.today()))

    async def get_today_subscription_lessons(self) -> Dict[str, Any]:
        """Уроки на сегодня для текущей подписки"""
        today = date.today()
        return await self._get_subscription_lessons(DateRange(today, today))

    async def get_tomorrow_subscription_lessons(self) -> Dict[str, Any]:
        """Уроки на завтра для текущей подписки"""
        tomorrow = date.today() + timedelta(days=1)
        return await self._get_subscription_lessons(DateRange(tomorrow, tomorrow))

    async def get_current_week_subscription_lessons(self) -> Dict[str, Any]:
        """Уроки на текущую неделю для подписки"""
        today = date.today()
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        return await self._get_subscription_lessons(DateRange(start_of_week, end_of_week))

    async def get_lessons_for_subscription(
            self,
            date_from: Optional[date] = None,
            date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """Уроки для подписки с произвольным диапазоном дат"""
        return await self._get_subscription_lessons(DateRange(date_from, date_to))

    # Внутренние методы реализации
    async def _get_lessons_with_range(
            self,
            obj_type: str,
            obj_id: str,
            date_range: DateRange,
    ) -> Dict[str, Any]:
        """Базовый метод для запросов по конкретному объекту"""
        endpoint = f"lessons/{obj_type}/{obj_id}/"
        return await self._make_lessons_request(endpoint, date_range)

    async def _get_subscription_lessons(
            self,
            date_range: DateRange,
    ) -> Dict[str, Any]:
        """Базовый метод для запросов по подписке пользователя"""
        endpoint = "lessons/me/"
        return await self._make_lessons_request(endpoint, date_range)

    async def _make_lessons_request(
        self,
            endpoint: str,
            date_range: DateRange,
    ) -> Dict[str, Any]:
        """
        Внутренний метод для выполнения запроса с диапазоном дат
        """
        params = {}

        if date_range.date_from:
            params["date_from"] = date_range.date_from.isoformat()
        if date_range.date_to:
            params["date_to"] = date_range.date_to.isoformat()

        try:
            response = await self.api_client.request(
                social_id=str(self.user.id),
                endpoint=endpoint,
                method="GET",
                params=params if params else None,
            )
            return response
        except Exception as e:
            logger.error(
                f"Failed to get lessons from {endpoint}. "
                f"Range: {date_range}. Error: {str(e)}",
                exc_info=True
            )
            return {"error": "Не удалось получить расписание"}
