from aiogram import BaseMiddleware

from telegrambot.dependencies import Container


class DependencyMiddleware(BaseMiddleware):
    def __init__(self, container: Container):
        super().__init__()
        self.container = container

    async def __call__(self, handler, event, data):
        # Передаём весь контейнер
        data["deps"] = self.container
        return await handler(event, data)
