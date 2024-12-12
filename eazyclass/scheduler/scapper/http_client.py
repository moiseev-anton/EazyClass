import asyncio
import logging

from aiohttp import ClientSession, ClientTimeout

logger = logging.getLogger(__name__)


class HttpClient:
    DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Connection": "keep-alive"
    }
    TIMEOUT = ClientTimeout(total=60, connect=10)

    def __init__(self, base_url: str = None, headers: dict = None, timeout: ClientTimeout = None):
        self.base_url = base_url
        self.headers = headers or self.DEFAULT_HEADERS
        self.timeout = timeout or self.TIMEOUT
        self.session = None

    async def __aenter__(self):
        self.session = ClientSession(base_url=self.base_url, timeout=self.timeout, headers=self.headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Закрытие сессии при выходе из контекста."""
        await self.close()

    # @retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=2, min=4, max=60), reraise=True)
    def ping_server(self, url=''):
        # Выполняем HEAD запрос, чтобы проверить доступность ресурса
        with self.session.head(url) as response:
            if response.status != 200:
                raise ValueError(f"Неверный код ответа: {response.status}")
            return response.status

    # @retry(stop=stop_after_attempt(3), wait=wait_random(1, 3), reraise=True)
    async def fetch_page_content(self, url: str) -> str:
        """
        Получение контента страницы.

        Args:
            url (str): Путь к странице относительно базового URL.

        Returns:
            str: HTML-контент страницы.

        Raises:
            ValueError: Если код ответа не равен 200.
        """
        logger.debug(f'Отправка запроса к {url}')
        async with self.session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Неверный код ответа: {response.status} при запросе к {url}")
            return await response.text()

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()


if __name__ == '__main__':
    async def make_head_request():
        url = "https://example.com"  # Замените на ваш URL
        async with HttpClient(base_url=url) as client:
            status = await client.ping_server()
            print("Код ответа:", status)


    asyncio.run(make_head_request())
