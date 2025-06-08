import asyncio
import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Dict, List, Tuple, Union

import aiohttp
import jsonapi_client
import yarl
from cachetools import TTLCache

from telegrambot.api_client.common_patch import camelize_name, decamelize_name
from telegrambot.api_client.document import CustomDocument
from telegrambot.api_client.document_fetcher import DocFetcher

import jsonapi_client.document

# Monkey-патч для jsonapi_client
jsonapi_client.common.jsonify_attribute_name = camelize_name
jsonapi_client.common.dejsonify_attribute_name = decamelize_name
jsonapi_client.document.Document = CustomDocument

from jsonapi_client import Filter, Inclusion
from jsonapi_client.common import HttpStatus, error_from_response, HttpMethod
from jsonapi_client.document import Document
from jsonapi_client.exceptions import DocumentError



logger = logging.getLogger(__name__)




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
        loop: Optional["AbstractEventLoop"] = None,
        use_relationship_iterator: bool = False,
        document_ttl: float = 3600,  # TTL для документов (1 час)
        resource_ttl: float = 3600,  # TTL для ресурсов (1 час)
        max_document_size: int = 1000,  # Максимум документов
        max_resource_size: int = 10000,  # Максимум ресурсов
        hmac_secret: Optional[str] = None,  # Secret key for HMAC authentication
        platform: str = "",
    ) -> None:
        super().__init__(
            server_url=server_url,
            enable_async=True,
            schema=schema,
            request_kwargs=request_kwargs,
            loop=loop,
            use_relationship_iterator=use_relationship_iterator,
        )

        self.documents_cache = TTLCache(maxsize=max_document_size, ttl=document_ttl)
        self.resources_by_id_cache = TTLCache(
            maxsize=max_resource_size, ttl=resource_ttl
        )
        self.resources_by_link_cache = TTLCache(
            maxsize=max_resource_size, ttl=resource_ttl
        )

        # Store TTL values for use in other methods
        self.document_ttl = document_ttl
        self.resource_ttl = resource_ttl

        # Store HMAC secret for authentication
        self.hmac_secret = hmac_secret.encode("utf-8") if hmac_secret else None
        self.platform = platform

    def build_url(
        self, resource_type: str, resource_id_or_filter: "Union[Modifier, str]" = None
    ) -> str:
        resource_id, filter_ = self._resource_type_and_filter(resource_id_or_filter)
        return self._url_for_resource(resource_type, resource_id, filter_)

    def _url_for_resource(
        self, resource_type: str, resource_id: str = None, filter: "Modifier" = None
    ) -> str:
        """
        Формирует url по имени ресурса и id и/или фильтрам.
        Адаптация метода. Добавляет / после id для избежания редиректа на сервере.
        """
        url = f"{self.url_prefix}/{resource_type}/"  # добавляем / в конце
        if resource_id is not None:
            url = f"{url}{resource_id}/"  # добавляем / в конце
        if filter:
            url = filter.url_with_modifiers(url)
        return yarl.URL(url)

    def _get_hmac_headers(
        self,
        method: str,
        url: str,
        social_id: str = "",
        body: Optional[bytes] = None,
        hmac_: bool = False,
    ) -> Dict[str, str]:
        headers = {"X-Platform": self.platform}
        if not social_id:
            return headers
        headers["X-Social-ID"] = social_id
        if hmac_ and self.hmac_secret:
            timestamp = str(int(time.time()))
            body_hash = hashlib.sha256(body or b"").hexdigest()

            message = f"{method}\n{url}\n{timestamp}\n{self.platform}\n{social_id}\n{body_hash}".encode(
                "utf-8"
            )
            signature = hmac.new(self.hmac_secret, message, hashlib.sha256).hexdigest()

            headers.update(
                {
                    "X-Signature": signature,
                    "X-Timestamp": timestamp,
                }
            )
        return headers

    @property
    def request_kwargs(self):
        return self._request_kwargs

    def cache_doc(self, url: str, document: Document) -> Optional[Document]:
        self.documents_cache[url] = document

    def add_resources(self, *resources: "ResourceObject") -> None:
        """Add resources to session cache."""
        for res in resources:
            self.resources_by_id_cache[(res.type, res.id)] = res
            if link := res.links.self.url if res.links.self else res.url:
                self.resources_by_link_cache[link] = res

    def remove_resource(self, res: "ResourceObject") -> None:
        del self.resources_by_id_cache[(res.type, res.id)]
        if link := res.links.self.url if res.links.self else res.url:
            if link in self.resources_by_link_cache:
                del self.resources_by_link_cache[link]

    async def fetch_document_by_url_async(
        self, url: str, social_id: str = "", hmac_: bool = False
    ) -> Document:
        """Fetch a Document from cache or server by URL, with ETag validation for cached document"""
        fetcher = DocFetcher(self, url, social_id, hmac_)
        return await fetcher.fetch()

    async def _get_async(
        self,
        resource_type: str,
        resource_id_or_filter: "Union[Modifier, str]" = None,
        social_id: str = "",
        hmac_: bool = False,
    ) -> "Document":
        resource_id, filter_ = self._resource_type_and_filter(resource_id_or_filter)
        url = self._url_for_resource(resource_type, resource_id, filter_)
        return await self.fetch_document_by_url_async(url)

    def get(
        self,
        resource_type: str,
        resource_id_or_filter: "Union[Modifier, str]" = None,
        social_id: str = "",
        hmac_: bool = False,
    ) -> "Union[Awaitable[Document], Document]":
        """
        Request (GET) Document from server.

        If session is used with enable_async=True, this needs
        to be awaited.
        """
        if self.enable_async:
            fetcher = DocFetcher(
                self, resource_type, resource_id_or_filter, social_id, hmac_
            )
            return fetcher.fetch()
        else:
            return self._get_sync(resource_type, resource_id_or_filter)

    async def fetch_resource_by_resource_identifier_async(
        self,
        resource: Union["ResourceIdentifier", "ResourceObject", "ResourceTuple"],
        cache_only=False,
        force=False,
    ) -> Optional["ResourceObject"]:
        """
        Internal use. Async version.

        Fetch resource from server by resource identifier.
        """
        type_, id_ = resource.type, resource.id
        new_res = not force and self.resources_by_id_cache.get((type_, id_))
        if new_res:
            return new_res
        elif cache_only:
            return None
        else:
            # Note: Document creation will add its resources to cache via .add_resources,
            # no need to do it manually here
            fetcher = DocFetcher(self, resource.url)
            return (await fetcher.ext_fetch_by_url_async()).resource

    def expire_caches(self) -> None:
        """Удаляет устаревшие записи из кэшей (для планировщика)."""
        self.documents_cache.expire()
        self.resources_by_id_cache.expire()
        self.resources_by_link_cache.expire()

    async def start(self) -> None:
        """Инициализация сессии."""
        if self._aiohttp_session is None or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.Session()
            logger.info("API client session started.")

    async def close(self):
        """Close session and clean cache."""
        self.invalidate()
        if self.enable_async and self._aiohttp_session:
            await self._aiohttp_session.close()

    def invalidate(self):
        """
        Invalidate resources and documents associated with this Session.
        """
        # TODO: Нам пока не надо инвалидировать все ресурсы, так как мы закрываем сессию только при остановке бота
        #  если в будущем понадобится, то можно рассмотреть вариант с флагом закрытия сессии
        #  и добавлением проверки этого флага во ресурсах и всех связанных с ними объектах.
        #  Так мы одним действием инвалидируем сразу всё.
        self.documents_cache.clear()
        self.resources_by_link_cache.clear()
        self.resources_by_id_cache.clear()

    async def http_request_async(
        self,
        http_method: str,
        url: str,
        send_json: dict = None,
        expected_statuses: List[str] = None,
        social_id: str = "",
        hmac_: bool = False,
    ) -> Tuple[int, dict, str]:
        """Method to make PATCH/POST requests to server using aiohttp library."""

        self.assert_async()
        logger.debug("%s request: %s", http_method.upper(), send_json)
        body_json = (
            json.dumps(send_json, ensure_ascii=False).encode("utf-8")
            if send_json
            else b""
        )
        expected_statuses = expected_statuses or HttpStatus.ALL_OK
        content_type = (
            "" if http_method == HttpMethod.DELETE else "application/vnd.api+json"
        )

        kwargs = {**self.request_kwargs}
        headers = {"Content-Type": "application/vnd.api+json"}
        headers.update(kwargs.pop("headers", {}))
        auth_headers = self._get_hmac_headers(
            http_method, url, social_id, body=body_json, hmac_=hmac_
        )
        headers.update(auth_headers)

        async with self._aiohttp_session.request(
            http_method, url, data=body_json, headers=headers, **kwargs
        ) as response:

            response_json = await response.json(content_type=content_type)
            if response.status not in expected_statuses:
                raise DocumentError(
                    f"Could not {http_method.upper()} "
                    f"({response.status}): "
                    f"{error_from_response(response_json)}",
                    errors={"status_code": response.status},
                    response=response,
                    json_data=send_json,
                )

            return (
                response.status,
                response_json or {},
                response.headers.get("Location"),
            )

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


async def check_client():
    s = AsyncClientSession(
        server_url="http://localhost:8010/api/v1/",
        hmac_secret="7zPMzWqOyA7xoGcez4ypqbZlHj70Kz6hGMPVVE3hMPc=",
        platform="telegram",
    )
    try:
        document = await s.get(
            "groups",
            Filter(grade=2) + Inclusion("faculty"),
            social_id="859901449",
            hmac_=False,
        )
        await s.get("groups", Filter(grade=2) + Inclusion("faculty"))
        # document = await s.get("users", 'me', social_id='859901449', hmac_=True)
        # user = document.resource
        # print(user.id)
        # print(user.username)
        # user.username = 'test'
        # user.commit(social_id='859901449', hmac_=True)
        # await s.get("groups", 5, social_id='859901449', hmac_=True)
        # print(s.resources_by_id_cache.values())
        # print(s.documents_cache.values())
    except Exception as e:
        raise
    finally:
        await s.close()
        print(s.resources_by_id_cache.values())
        print(s.documents_cache.values())


if __name__ == "__main__":
    asyncio.run(check_client())
