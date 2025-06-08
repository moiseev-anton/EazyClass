import copy
import logging
from urllib.parse import parse_qsl, urlencode, urlunparse

from jsonapi_client.document import Document

from jsonapi_client.common import HttpStatus, error_from_response
from jsonapi_client.exceptions import DocumentError

logger = logging.getLogger(__name__)


# class NotModifiedError(Exception):
#     """Raised when server responds with HTTP 304 Not Modified"""
#
#     pass


class DocFetcher:
    def __init__(
        self,
        client: 'AsyncClientSession',
        resource_type: str,
        resource_id_or_filter: 'Union[Modifier, str]' = None,
        social_id: str = None,
        hmac: bool = False,
        no_cache: bool = False,
    ) -> None:
        self.client = client
        self.url = client.build_url(resource_type, resource_id_or_filter)
        self.social_id = social_id
        self.hmac_ = hmac
        self.no_cache = no_cache
        self._request_kwargs = {**client.request_kwargs}
        self.new_etag = None
        self.json = None
        self.doc = None

    def _update_request_headers(self, new_headers: dict):
        headers = self._request_kwargs.setdefault("headers", {})
        headers.update(new_headers)

    async def fetch(self) -> 'Document':
        if document := self.client.documents_cache.get(self.url):
            if not document.etag:
                return document  # Без ETag, просто используем кешированный документ
            self._update_request_headers({"If-None-Match": document.etag})

        try:
            return await self.ext_fetch_by_url_async()
        except NotModifiedError:
            return document

    async def ext_fetch_by_url_async(self) -> "Document":
        await self._fetch_json_async()
        return await self.read()

    async def _fetch_json_async(self):
        logger.info(f"Fetching document from url {self.url}")

        auth_headers = self.client._get_hmac_headers("GET", self.url, self.social_id, hmac_=self.hmac_)
        self._update_request_headers(auth_headers)

        async with self.client._aiohttp_session.get(
            self.url, **self._request_kwargs
        ) as response:
            if response.status == 304:
                raise NotModifiedError("Document not modified")

            response_content = await response.json(
                content_type="application/vnd.api+json"
            )

            if response.status == HttpStatus.OK_200:
                self.new_etag = response.headers.get("ETag")
                self.json = response_content
                return self.json

            raise DocumentError(
                f"Error {response.status}: " f"{error_from_response(response_content)}",
                errors={"status_code": response.status},
                response=response,
            )

    async def read(self) -> "Document":
        self.doc = Document(
            self.client, self.json, self.url, etag=self.new_etag, no_cache=self.no_cache
        )
        if not self.no_cache:
            self.client.cache_doc(self.url, self.doc)
        return self.doc
