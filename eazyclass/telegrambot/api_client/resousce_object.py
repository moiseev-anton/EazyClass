from typing import Union, Awaitable, Optional

from jsonapi_client.resourceobject import ResourceObject
from .commit_executor import CommitExecutor


class Resource(ResourceObject):
    @property
    def http_method(self):
        return self._http_method

    @property
    def is_deleted(self):
        return self._delete

    def commit(self, custom_url: str = '', meta: dict = None, social_id: str = '', hmac_: bool = False) -> Union[None, ResourceObject, Awaitable[Optional[ResourceObject]]]:
        """
        Commit (PATCH/POST) this resource to server.
        If in async mode, this needs to be awaited.
        """

        if self.session.enable_async:
            executor = CommitExecutor(self, custom_url, meta, social_id, hmac_)
            return executor.execute()
        else:
            return self._commit_sync(custom_url, meta)
