import asyncio
import hashlib
import hmac
import json
import logging
import time
import copy
from typing import Optional, Dict, Any, List
from jsonapi_client import Session as JsonApiSession, Filter, Inclusion
from jsonapi_client.common import HttpStatus, error_from_response
from jsonapi_client.document import Document
from jsonapi_client import common

from aiocache import SimpleMemoryCache
import aiohttp

import jsonapi_client
from jsonapi_client.exceptions import DocumentError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_fixed,
    retry_if_exception_type,
    wait_exponential,
)

logger = logging.getLogger(__name__)


def camelize_name(name: str) -> str:
    parts = name.split('_')
    return parts[0] + ''.join(p.capitalize() for p in parts[1:])


def decamelize_name(name: str) -> str:
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()


# Monkey-патч для jsonapi_client:
# По умолчанию библиотека превращает поля с подчеркиваниями (short_title) в JSON-ключи с дефисами (short-title).
# Так как DRF JSON API настроен на camelCase (shortTitle), переопределяем функции сериализации,
# чтобы атрибуты корректно отображались и были доступны как обычные свойства: faculty.short_title.
common.jsonify_attribute_name = camelize_name
common.dejsonify_attribute_name = decamelize_name


class NotModifiedError(Exception):
    """Raised when server responds with HTTP 304 Not Modified"""
    pass


class Document(jsonapi_client.document.Document):
    def __init__(self, session: 'Session',
                 json_data: dict,
                 url: str,
                 etag: str = None,
                 no_cache: bool=False) -> None:
        super().__init__(session, json_data, url, no_cache)
        self._etag = etag

    @property
    def etag(self) -> str:
        return self._etag

    @property
    def enable_async(self) -> bool:
        return getattr(self.session, "enable_async", False)


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

    async def get_headers(
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


# class HmacJsonApiClient(jsonapi_client.Session):
#     def __init__(
#         self,
#         server_url: str,
#         hmac_secret: str,
#         platform: Optional[str] = None,
#         bot_social_id: Optional[str] = None,
#         timeout: Optional[aiohttp.ClientTimeout] = None,
#         connector: Optional[aiohttp.TCPConnector] = None,
#         *args,
#         **kwargs,
#     ):
#         super().__init__(server_url=server_url, enable_async=True, *args, **kwargs)
#         self.hmac_auth = HMACAuth(
#             secret=hmac_secret, platform=platform, bot_social_id=bot_social_id
#         )
#         self.timeout = timeout or aiohttp.ClientTimeout(
#             total=10, connect=3, sock_read=5
#         )
#         self.connector = connector or aiohttp.TCPConnector(
#             limit=100, limit_per_host=10, ssl=True
#         )
#         self._aiohttp_session = None
#         self._ensure_session()
#
#     def _ensure_session(self):
#         """Создаёт или восстанавливает http-сессию, если она закрыта."""
#         if self._aiohttp_session is None or self._aiohttp_session.closed:
#             self._aiohttp_session = aiohttp.ClientSession(
#                 timeout=self.timeout,
#                 connector=self.connector,
#             )
#             logger.info("Session created")
#
#     @retry(
#         stop=stop_after_attempt(5),  # До 5 попыток
#         wait=wait_exponential(
#             multiplier=1, min=1, max=10
#         ),  # Экспоненциальная задержка: 1, 2, 4, 8, 10 сек
#         retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
#         reraise=True,
#     )
#     async def http_request_async(
#         self,
#         http_method: str,
#         url: str,
#         send_json: dict,
#         expected_statuses: List[str] = None,
#         social_id: Optional[str] = None,
#     ):
#         self._ensure_session()
#         body_json = (
#             json.dumps(send_json, ensure_ascii=False).encode("utf-8")
#             if send_json
#             else b""
#         )
#         headers = await self.hmac_auth.get_headers(
#             method=http_method,
#             url=url,
#             social_id=social_id,
#             body=body_json,
#         )
#         self._request_kwargs["headers"] = headers
#         try:
#             return await super().http_request_async(
#                 http_method, url, send_json, expected_statuses
#             )
#         except Exception as e:
#             logger.error(f"Request failed: {str(e)}")
#             raise
#
#     async def close(self):
#         await super().close()
#         logger.info("JSON:API session closed.")


class AsyncClientSession(jsonapi_client.Session):
    def __init__(
        self,
        server_url: str = None,
        schema: dict = None,
        request_kwargs: dict = None,
        loop: Optional['AbstractEventLoop'] = None,
        use_relationship_iterator: bool = False,
        document_ttl: float = 900.0,  # TTL for documents in seconds (15 minutes)
        resource_ttl: float = 930.0,  # TTL for resources in seconds (15.5 minutes)
        hmac_secret: Optional[str] = None,  # Secret key for HMAC authentication
        platform: str = None,
    ) -> None:
        super().__init__(
            server_url=server_url,
            enable_async=True,
            schema=schema,
            request_kwargs=request_kwargs,
            loop=loop,
            use_relationship_iterator=use_relationship_iterator,
        )

        # Initialize TTL-enabled caches using aiocache.SimpleMemoryCache
        self.documents_cache = SimpleMemoryCache()  # Cache for documents by URL
        self.resources_by_id_cache = SimpleMemoryCache()  # Cache for resources by (type, id)
        self.resources_by_link_cache = SimpleMemoryCache()  # Cache for resources URL

        # Store TTL values for use in other methods
        self.document_ttl = document_ttl
        self.resource_ttl = resource_ttl

        # Store HMAC secret for authentication
        self.hmac_secret = hmac_secret
        self.platform = platform

    @property
    def request_kwargs(self):
        return self._request_kwargs

    async def cache_doc(self, url: str, document: Document, ttl: int = None) -> Optional[Document]:
        return await self.documents_cache.set(key=url, value=document, ttl=ttl or self.document_ttl)

    async def add_resources(self, *resources: 'ResourceObject') -> None:
        """Add resources to session cache."""
        for res in resources:
            await self.resources_by_id_cache.set(key=(res.type, res.id), value=res)
            if link := res.links.self.url if res.links.self else res.url:
                await self.resources_by_link_cache.set(key=link, value=res)

    async def remove_resource(self, res: 'ResourceObject') -> None:
        """Add resources to session cache."""
        await self.resources_by_id_cache.delete(key=(res.type, res.id))
        await self.resources_by_link_cache.delete(key=res.url)

    async def fetch_document_by_url_async(self, url: str) -> Document:
        """Fetch a Document from cache or server by URL, with ETag validation for cached document"""
        fetcher = DocFetcher(self, url)
        return await fetcher.fetch()

    async def fetch_resource_by_resource_identifier_async(
                self,
                resource: 'Union[ResourceIdentifier, ResourceObject, ResourceTuple]',
                cache_only=False,
                force=False) -> 'Optional[ResourceObject]':
        """
        Internal use. Async version.

        Fetch resource from server by resource identifier.
        """
        type_, id_ = resource.type, resource.id
        new_res = not force and await self.resources_by_id_cache.get((type_, id_))
        if new_res:
            return new_res
        elif cache_only:
            return None
        else:
            # Note: Document creation will add its resources to cache via .add_resources,
            # no need to do it manually here
            fetcher = DocFetcher(self, resource.url)
            return (await fetcher.ext_fetch_by_url_async()).resource

    async def close(self):
        """Close session and clean cache."""
        await self.invalidate()
        if self.enable_async and self._aiohttp_session:
            await self._aiohttp_session.close()

    async def invalidate(self):
        """
        Invalidate resources and documents associated with this Session.
        """
        # TODO: Нам пока не надо инвалидировать все ресурсы, так как мы закрываем сессию только при остановке бота
        #  если в будущем понадобится, то можно рассмотреть вариант с флагом закрытия сессии
        #  и добавлением проверки этого флага во ресурсах и всех связанных с ними объектах.
        #  Так мы одним действием инвалидируем сразу всё.
        await self.documents_cache.clear()
        await self.resources_by_link_cache.clear()
        await self.resources_by_id_cache.clear()

    # async def fetch_document_by_url_async(self, url: str) -> 'Document':
    #     """
    #     Fetch a Document from the cache or server by URL, with ETag support.
    #
    #
    #
    #     First checks the documents_cache. If not found, checks etag_cache and sends a request
    #     with If-None-Match. If the server responds with 304, uses the cached document.
    #     If 200, updates the document and ETag in their respective caches.
    #     """
    #     # Check if document is in cache
    #     document = await self.documents_cache.get(url)
    #     if document:
    #         return document
    #
    #     # Check if ETag is available for conditional request
    #     etag = await self.etag_cache.get(url)
    #     headers = {'If-None-Match': etag} if etag else {}
    #
    #     try:
    #         # Perform request with headers
    #         json_data = await self._fetch_json_async(url, method='GET', headers=headers)
    #         # If we get here, it's a 200 response with new data
    #         document = self.read(json_data, url)
    #         # Cache the document and ETag
    #         await self.documents_cache.set(url, document, ttl=self.document_ttl)
    #         new_etag = json_data.get('headers', {}).get('ETag')
    #         if new_etag:
    #             await self.etag_cache.set(url, new_etag, ttl=self.etag_ttl)
    #         return document
    #
    #     except aiohttp.ClientResponseError as e:
    #         if e.status == 304:  # Not Modified
    #             # Use cached document if available
    #             document = await self.documents_cache.get(url)
    #             if document:
    #                 return document
    #             # If no cached document, fall back to full request without ETag
    #             json_data = await self._fetch_json_async(url, method='GET')
    #             document = self.read(json_data, url)
    #             await self.documents_cache.set(url, document, ttl=self.document_ttl)
    #             new_etag = json_data.get('headers', {}).get('ETag')
    #             if new_etag:
    #                 await self.etag_cache.set(url, new_etag, ttl=self.etag_ttl)
    #             return document
    #         raise  # Re-raise other HTTP errors

    async def start(self) -> None:
        """Инициализация сессии."""
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.Session()
            logger.info("API client session started.")

    # async def close(self) -> None:
    #     """Закрытие сессии."""
    #     if self.session and not self.session.closed:
    #         await self.session.close()
    #         logger.info("API client session closed.")

    # def _generate_hmac_headers(
    #     self, method: str, url: str, body_json: bytes, social_id: str
    # ) -> Dict[str, str]:
    #     """Генерирует HMAC-заголовки для запроса."""
    #     timestamp = str(int(time.time()))
    #     body_hash = hashlib.sha256(body_json).hexdigest()
    #     message = f"{method}\n{url}\n{timestamp}\n{self.platform}\n{social_id}\n{body_hash}".encode(
    #         "utf-8"
    #     )
    #     signature = hmac.new(self.hmac_secret, message, hashlib.sha256).hexdigest()
    #     return {
    #         "X-Signature": signature,
    #         "X-Timestamp": timestamp,
    #         "X-Platform": self.platform,
    #         "X-Social-ID": social_id,
    #         "Content-Type": "application/json",
    #     }

    # # Повторные попытки запроса
    # @retry(
    #     stop=stop_after_attempt(3),
    #     wait=wait_fixed(1),
    #     retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
    #     reraise=True,
    # )
    # async def _send_request(
    #     self,
    #     method: str,
    #     url: str,
    #     body_json: bytes,
    #     headers: dict,
    #     params: Optional[dict] = None,
    # ) -> Dict[str, Any]:
    #     """Отправка запроса."""
    #     async with self.session.request(
    #         method, url, data=body_json, headers=headers, params=params
    #     ) as response:
    #         if response.status != 200:
    #             error_text = await response.text()
    #             logger.error(f"API error: {response.status} - {error_text}")
    #             raise aiohttp.ClientResponseError(
    #                 response.request_info,
    #                 response.history,
    #                 status=response.status,
    #                 message=error_text,
    #             )
    #         return await response.json()
    #
    # async def request(
    #     self,
    #     social_id,
    #     endpoint: str,
    #     method: str = "POST",
    #     payload: Dict[str, Any] = None,
    #     params: Optional[dict] = None,
    # ) -> Dict[str, Any]:
    #     """Выполняет запрос к Django API с HMAC-подписью."""
    #     if not self.session or self.session.closed:
    #         await self.start()
    #
    #     url = urljoin(self.base_url, endpoint)
    #     body_json = (
    #         json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else b""
    #     )
    #     headers = self._generate_hmac_headers(method, url, body_json, social_id)
    #
    #     try:
    #         return await self._send_request(
    #             method, url, body_json, headers, params=params
    #         )
    #     except (aiohttp.ClientError, asyncio.TimeoutError) as e:
    #         logger.error(f"Request failed after retries: {str(e)}")
    #         raise


class DocFetcher:
    def __init__(self, client: AsyncClientSession, url: str, no_cache: bool = False) -> None:
        self.client = client
        self.url = url
        self.no_cache = no_cache
        self._request_kwargs = copy.deepcopy(client.request_kwargs)
        self.old_etag = None
        self.new_etag = None
        self.json = None
        self.doc = None

    async def fetch(self) -> 'Document':
        if document := await self.client.documents_cache.get(self.url):
            if not document.etag:
                return document  # Без ETag, просто используем кешированный документ
            self.old_etag = document.etag
            self._request_kwargs.setdefault("headers", {})
            self._request_kwargs["headers"]["If-None-Match"] = self.old_etag

        try:
            return await self.ext_fetch_by_url_async()
        except NotModifiedError:
            return document

    async def ext_fetch_by_url_async(self) -> 'Document':
        await self._fetch_json_async()
        return await self.read()

    async def _fetch_json_async(self):
        from urllib.parse import urlparse
        parsed_url = urlparse(self.url)
        logger.info(f'Fetching document from url {parsed_url}')

        async with self.client._aiohttp_session.get(parsed_url.geturl(), **self._request_kwargs) as response:
            if response.status == 304:
                raise NotModifiedError("Document not modified")

            response_content = await response.json(content_type='application/vnd.api+json')

            if response.status == HttpStatus.OK_200:
                self.new_etag = response.headers.get("ETag")
                self.json = response_content
                return self.json

            raise DocumentError(f'Error {response.status}: '
                                f'{error_from_response(response_content)}',
                                errors={'status_code': response.status},
                                response=response)

    async def read(self) -> 'Document':
        self.doc = Document(self.client, self.json, self.url, etag=self.new_etag, no_cache=self.no_cache)
        if not self.no_cache:
            await self.client.cache_doc(self.url, self.doc)
        return self.doc

    # Perform request
        # try:
        #     json_data = await self.client._fetch_json_async(self.url, method='GET', headers=self.headers)
        #     # Handle 200 response
        #     document = self.client.read(json_data, self.url)
        #     await self.client.documents_cache.set(self.url, document, ttl=self.client.document_ttl)
        #     new_etag = json_data.get('headers', {}).get('ETag')
        #     if new_etag:
        #         await self.client.etag_cache.set(self.url, new_etag, ttl=self.client.etag_ttl)
        #     return document
        # except aiohttp.ClientResponseError as e:
        #     if e.status == 304 and document:
        #         return document  # Use cached document
        #     raise  # Re-raise other errors


async def check_client():
    s = AsyncClientSession(server_url="http://localhost:8010/api/v1/")
    document = await s.get("groups", Filter(grade=2) + Inclusion("faculty"))
    await s.get("groups", Filter(grade=2) + Inclusion("faculty"))
    await s.close()

if __name__ == '__main__':
    # asyncio.run(check_client())
    print(jsonapi_client.__file__)
