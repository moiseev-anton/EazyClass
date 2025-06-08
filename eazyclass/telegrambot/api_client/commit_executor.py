import logging
from typing import Optional

from jsonapi_client.common import HttpMethod
from .resousce_object import Resource

logger = logging.getLogger(__name__)


class CommitExecutor:
    def __init__(
        self,
        resource: Resource,
        url: str = '',
        meta: dict = None,
        social_id: str = '',
        hmac_: bool = False,
    ):
        self.resource = resource
        self.client = resource.session
        self._http_method = resource.http_method
        self.url = resource._pre_commit(url)
        self.send_json = resource._commit_data(meta)
        self.social_id = social_id
        self.hmac = hmac_

    async def execute(self) -> None:
        self.client.assert_async()
        if self.resource.is_deleted:
            return await self._perform_delete_async()

        status, result, location = await self.client.http_request_async(
                                                self._http_method,
                                                self.url,
                                                self.send_json,
                                                social_id=self.social_id,
                                                hmac_=self.hmac
        )
        return self.client._post_commit(status, result, location)

    async def _perform_delete_async(self):
        await self.client.http_request_async(
            HttpMethod.DELETE,
            self.url,
            social_id=self.social_id,
            hmac_=self.hmac)
        self.client.remove_resource(self)

