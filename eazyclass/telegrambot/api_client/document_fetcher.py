import copy
import logging
from .document import CustomDocument

from jsonapi_client.common import HttpStatus, error_from_response
from jsonapi_client.exceptions import DocumentError

logger = logging.getLogger(__name__)


class NotModifiedError(Exception):
    """Raised when server responds with HTTP 304 Not Modified"""

    pass


class DocFetcher:
    def __init__(
        self, client: 'AsyncClientSession', url: str, no_cache: bool = False
    ) -> None:
        self.client = client
        self.url = url
        self.no_cache = no_cache
        self._request_kwargs = copy.deepcopy(client.request_kwargs)
        self.old_etag = None
        self.new_etag = None
        self.json = None
        self.doc = None

    async def fetch(self) -> 'CustomDocument':
        if document := self.client.documents_cache.get(self.url):
            if not document.etag:
                return document  # Без ETag, просто используем кешированный документ
            self.old_etag = document.etag
            self._request_kwargs.setdefault("headers", {})
            self._request_kwargs["headers"]["If-None-Match"] = self.old_etag

        try:
            return await self.ext_fetch_by_url_async()
        except NotModifiedError:
            return document

    async def ext_fetch_by_url_async(self) -> "CustomDocument":
        await self._fetch_json_async()
        return await self.read()

    async def _fetch_json_async(self):
        from urllib.parse import urlparse

        parsed_url = urlparse(self.url)
        logger.info(f"Fetching document from url {parsed_url}")

        async with self.client._aiohttp_session.get(
            parsed_url.geturl(), **self._request_kwargs
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

    async def read(self) -> "CustomDocument":
        self.doc = CustomDocument(
            self.client, self.json, self.url, etag=self.new_etag, no_cache=self.no_cache
        )
        if not self.no_cache:
            self.client.cache_doc(self.url, self.doc)
        return self.doc
