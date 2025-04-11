import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Dict, Any
from urllib.parse import urljoin

import aiohttp
from tenacity import retry, stop_after_attempt, wait_fixed, retry_if_exception_type

logger = logging.getLogger(__name__)


class ApiClient:
    def __init__(
        self, base_url: str, hmac_secret: str, platform: str, bot_social_id: str
    ):
        self.base_url = base_url
        self.hmac_secret = hmac_secret.encode("utf-8")
        self.platform = platform
        self.bot_social_id = bot_social_id
        self.session: Optional[aiohttp.ClientSession] = None
        self.timeout = aiohttp.ClientTimeout(total=10, connect=3, sock_read=5)

    async def start(self) -> None:
        """Инициализация сессии."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            logger.info("API client session started.")

    async def close(self) -> None:
        """Закрытие сессии."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.info("API client session closed.")

    def _generate_hmac_headers(
        self, method: str, url: str, body_json: bytes, social_id: str
    ) -> Dict[str, str]:
        """Генерирует HMAC-заголовки для запроса."""
        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body_json).hexdigest()
        message = f"{method}\n{url}\n{timestamp}\n{self.platform}\n{social_id}\n{body_hash}".encode(
            "utf-8"
        )
        signature = hmac.new(self.hmac_secret, message, hashlib.sha256).hexdigest()
        return {
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "X-Platform": self.platform,
            "X-Social-ID": social_id,
            "Content-Type": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
        reraise=True,
    )
    async def _send_request(
        self,
        method: str,
        url: str,
        body_json: bytes,
        headers: dict,
        params: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Отправка запроса с повторными попытками."""
        async with self.session.request(
            method, url, data=body_json, headers=headers, params=params
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                logger.error(f"API error: {response.status} - {error_text}")
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=error_text,
                )
            return await response.json()

    async def request(
        self,
        social_id,
        endpoint: str,
        method: str = "POST",
        payload: Dict[str, Any] = None,
        params: Optional[dict] = None,
    ) -> Dict[str, Any]:
        """Выполняет запрос к Django API с HMAC-подписью."""
        if not self.session or self.session.closed:
            await self.start()

        url = urljoin(self.base_url, endpoint)
        body_json = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else b""
        )
        headers = self._generate_hmac_headers(method, url, body_json, social_id)

        try:
            return await self._send_request(
                method, url, body_json, headers, params=params
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            logger.error(f"Request failed after retries: {str(e)}")
            raise

    async def bot_request(
        self,
        endpoint: str,
        method: str = "POST",
        payload: Dict[str, Any] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        return await self.request(self.bot_social_id, endpoint, method, payload, params)
