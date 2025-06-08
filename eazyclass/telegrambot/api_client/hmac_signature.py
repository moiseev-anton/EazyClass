from typing import Optional, Dict
import hashlib
import hmac
import time


class HMACAuth:
    """
    Генератор HMAC-заголовков
    для персонифицированных запросов (с пользовательским social_id).
    """

    def __init__(
        self,
        secret: str,
        platform: str,
    ):
        self.secret = secret.encode("utf-8")
        self.platform = platform

    async def get_hmac_headers(
        self,
        method: str,
        url: str,
        social_id: str,
        body: Optional[bytes] = None,
    ) -> Dict[str, str]:
        """Возвращает заголовки для запроса."""

        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body or b"").hexdigest()
        message = f"{method}\n{url}\n{timestamp}\n{self.platform}\n{social_id}\n{body_hash}".encode(
            "utf-8"
        )
        signature = hmac.new(self.secret, message, hashlib.sha256).hexdigest()

        return {
            "X-Signature": signature,
            "X-Timestamp": timestamp,
            "X-Platform": self.platform,
            "X-Social-ID": social_id,
        }
