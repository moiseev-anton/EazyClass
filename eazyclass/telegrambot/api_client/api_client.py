from telegrambot.api_client.contextual_prefixed_cache import ContextualCache
from telegrambot.api_client.thunder_protection import thunder_protection

import jsonapi_client
from telegrambot.api_client.client_patch import camelize_attribute_name, decamelize_attribute_name
from telegrambot.api_client.document import CustomDocument
# Monkey-патч для jsonapi_client
jsonapi_client.common.jsonify_attribute_name = camelize_attribute_name
jsonapi_client.common.dejsonify_attribute_name = decamelize_attribute_name
jsonapi_client.document.Document = CustomDocument

import asyncio
import copy
import hashlib
import hmac
import json
import logging
import time
from typing import Optional, Dict, List, Tuple, Any

import jsonapi_client.document
import yarl
from jsonapi_client import Filter, Inclusion
from jsonapi_client.common import HttpStatus, error_from_response, HttpMethod
from jsonapi_client.document import Document
from jsonapi_client.exceptions import DocumentError
from telegrambot.api_client.exceptions import NotModifiedError
from telegrambot.context import request_context


logger = logging.getLogger(__name__)


class AsyncClientSession(jsonapi_client.Session):
    def __init__(
        self,
        server_url: str,
        platform: str,
        hmac_secret: Optional[str],
        schema: dict = None,
        request_kwargs: dict = None,
        use_relationship_iterator: bool = False,
    ) -> None:
        request_kwargs = request_kwargs or {}

        # Устанавливаем X-Platform в заголовки, если он еще не установлен
        headers = request_kwargs.setdefault("headers", {})
        headers.setdefault("X-Platform", platform)

        super().__init__(
            server_url=server_url,
            enable_async=True,
            schema=schema,
            request_kwargs=request_kwargs,
            use_relationship_iterator=use_relationship_iterator,
        )

        self.resources_by_resource_identifier = ContextualCache(maxsize=10_000, ttl=600)
        self.resources_by_link = ContextualCache(maxsize=10_000, ttl=600)
        self.documents_by_link = ContextualCache(maxsize=10_000, ttl=600)

        self.hmac_secret = hmac_secret.encode("utf-8") if hmac_secret else None
        self.platform = platform

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
    ) -> Dict[str, str]:
        if not self.hmac_secret or not social_id:
            return {}

        timestamp = str(int(time.time()))
        body_hash = hashlib.sha256(body or b"").hexdigest()
        message = f"{method.upper()}\n{url}\n{timestamp}\n{self.platform}\n{social_id}\n{body_hash}".encode("utf-8")
        signature = hmac.new(self.hmac_secret, message, hashlib.sha256).hexdigest()
        # logger.info(message)

        return {
            "X-Signature": signature,
            "X-Timestamp": timestamp,
        }

    def _build_authenticated_request_kwargs(
            self,
            method: str,
            url: str,
            body: Optional[bytes] = None,
    ) -> Dict[str, Any]:
        ctx = request_context.get({})
        social_id = ctx.get("user_id")
        use_hmac = ctx.get("hmac", False)

        # Пока deepcopy не даёт накладных расходов, используем его
        # для устойчивости при возможном расширении request_kwargs
        kwargs = copy.deepcopy(self._request_kwargs)
        headers = kwargs.setdefault("headers", {})

        if social_id:
            headers["X-Social-ID"] = social_id
            if use_hmac:
                hmac_headers = self._get_hmac_headers(method, url, social_id, body)
                headers.update(hmac_headers)

        if method in (HttpMethod.POST, HttpMethod.PATCH):
            headers['Content-Type'] = 'application/vnd.api+json'

        return kwargs

    async def fetch_document_by_url_async(self, url: str) -> 'Document':
        """Fetch a Document from cache or server by URL, with ETag validation for cached document"""
        if document := self.documents_by_link.get(url):
            if not document.etag:
                return document  # Без ETag просто используем кешированный документ

        try:
            return await self._ext_fetch_by_url_async(url)
        except NotModifiedError:
            return document

    @thunder_protection(prefix="_ext_fetch_by_url_async")
    async def _ext_fetch_by_url_async(self, url: str) -> 'Document':
        json_data, etag = await self._fetch_json_async(url)
        return self.read(json_data, url, etag=etag)

    def read(self, json_data: dict, url='', etag=None, no_cache=False) -> 'Document':
        """Read document from json_data dictionary instead of fetching it from the server."""
        from telegrambot.api_client.document import CustomDocument
        doc = self.documents_by_link[url] = CustomDocument(self, json_data, url, etag=etag, no_cache=no_cache)
        return doc

    async def _fetch_json_async(self, url: str) -> Tuple[dict, Optional[str]]:
        """
        Internal use. Async version.

        Fetch document raw json from server using aiohttp library.
        """
        self.assert_async()
        logger.info('Fetching document from url %s', url)

        request_kwargs = self._build_authenticated_request_kwargs("GET", url)
        if document := self.documents_by_link.get(url):
            if document_etag := document.etag:
                headers = request_kwargs.setdefault("headers", {})
                headers["If-None-Match"] = document_etag
        logger.debug("Request headers: %s", **request_kwargs.get("headers", {}))

        async with self._aiohttp_session.get(url, **request_kwargs) as response:
            if response.status == 304:
                raise NotModifiedError("Document not modified")

            response_content = await response.json(content_type='application/vnd.api+json')

            if response.status == HttpStatus.OK_200:
                new_etag = response.headers.get("ETag")
                return response_content, new_etag
            else:
                raise DocumentError(f'Error {response.status}: '
                                    f'{error_from_response(response_content)}',
                                    errors={'status_code': response.status},
                                    response=response)

    async def http_request_async(
        self,
        http_method: str,
        url: str,
        send_json: dict = None,
        expected_statuses: List[str] = None,
    ) -> Tuple[int, dict, str]:
        """Method to make PATCH/POST requests to server using aiohttp library."""

        self.assert_async()
        logger.debug("%s request: %s", http_method.upper(), send_json)
        expected_statuses = expected_statuses or HttpStatus.ALL_OK
        content_type = "" if http_method == HttpMethod.DELETE else "application/vnd.api+json"

        body_bytes = json.dumps(send_json, ensure_ascii=False).encode("utf-8") if send_json else b""

        request_kwargs = self._build_authenticated_request_kwargs(http_method, url, body_bytes)
        logger.debug("Request headers: %s", **request_kwargs.get("headers", {}))

        async with self._aiohttp_session.request(http_method, url, data=body_bytes, **request_kwargs) as response:
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


async def user_request(client, name: str, user_id: str, hmac_enabled: bool, delay: float = 0):
    # Устанавливаем контекст
    token = request_context.set({
        "user_id": user_id,
        "hmac": hmac_enabled
    })

    try:
        print(f"[{name}] Запуск запроса через {delay} сек...")
        await asyncio.sleep(delay)

        doc = await client.get("groups", Filter(grade=2) + Inclusion("faculty"))

        # print(f"[{name}] Документ: {doc}\n")

        print(f"[{name}] Кэш документов после запроса:")
        for k, v in client.documents_by_link.items():  # client.cache должен быть твоим PrefixedCache
            print(f"   {k} -> {type(v)}")
        print("-" * 50)

        print(f"[{name}] Кэш ресурсов по id после запроса:")
        for k, v in client.resources_by_resource_identifier.items():  # client.cache должен быть твоим PrefixedCache
            print(f"   {k} -> {type(v)}")
        print("-" * 50)

        print(f"[{name}] Кэш ресурсов по link после запроса:")
        for k, v in client.resources_by_link.items():  # client.cache должен быть твоим PrefixedCache
            print(f"   {k} -> {type(v)}")
        print("-" * 50)

    finally:
        # Всегда восстанавливаем старый контекст
        request_context.reset(token)


async def check_client():
    s = AsyncClientSession(
        server_url="http://localhost:8010/api/v1/",
        hmac_secret="<some_secret>",
        platform="telegram",
    )
    try:
        async def user1_session(client):
            await user_request(client, "User1 - первый запрос", "user1", hmac_enabled=True)
            await asyncio.sleep(5)
            await user_request(client, "User1 - второй запрос", "user1", hmac_enabled=False)

        # Вторая корутина: пользователь 2 запускается через 1 секунду
        async def user2_session(client):
            await asyncio.sleep(1)
            tasks = [
                user_request(client, "User2 - 1", "user2", hmac_enabled=False),
                user_request(client, "User2 - 2", "user2", hmac_enabled=True),
                user_request(client, "User4", "user4", hmac_enabled=False),
                user_request(client, "User5", "user5", hmac_enabled=False),
                user_request(client, "User6", "user6", hmac_enabled=False),
            ]
            await asyncio.gather(*tasks)

        await asyncio.gather(
            user1_session(s),
            user2_session(s)
        )
    except Exception as e:
        raise
    finally:
        await s.close()


if __name__ == "__main__":
    asyncio.run(check_client())
