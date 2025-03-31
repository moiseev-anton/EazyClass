from aiogram import BaseMiddleware, types
from typing import Callable, Dict, Any, Awaitable
from telegrambot.dependencies import Container


class DependencyMiddleware(BaseMiddleware):
    def __init__(self, container: Container):
        super().__init__()
        self.container = container

    async def __call__(self, handler, event, data):
        # Передаём весь контейнер
        data["container"] = self.container
        return await handler(event, data)
