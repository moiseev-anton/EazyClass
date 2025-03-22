import aiohttp
import os

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000/api")


class BackendClient:
    def __init__(self, base_url, token=None):
        self.base_url = base_url
        self.headers = {"Authorization": f"Bearer {token}"} if token else {}
        self.session = None

    async def start(self):
        """Инициализация сессии"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()


    async def close(self):
        """Закрытие сессии"""
        if self.session and not self.session.closed:
            await self.session.close()

    async def request(self, endpoint, method="GET", data=None):
        async with aiohttp.ClientSession(headers=self.headers) as session:
            url = f"{self.base_url}/{endpoint}"
            async with session.request(method, url, json=data) as response:
                return await response.json()