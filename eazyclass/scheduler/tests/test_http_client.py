from contextlib import nullcontext as does_not_raise

import pytest
from aiohttp import ClientSession
from aioresponses import aioresponses

from scheduler.scapper.http_client import HttpClient


class TestHttpClient:

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "base_url",
        [
            "https://example.com",
            None,
        ]
    )
    async def test_http_client_init(self, base_url):
        async with HttpClient(base_url=base_url) as client:
            assert isinstance(client.session, ClientSession)
            assert client.base_url == base_url
            assert str(client.session._base_url) == str(base_url)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url, status, expectation", [
        ("https://example.com", 200, does_not_raise()),
        ("https://example.com", 404, pytest.raises(ValueError)),
    ])
    async def test_ping_server(self, url, status, expectation):
        with aioresponses() as m:
            m.head(url, status=status)
            async with HttpClient() as client:
                with expectation:
                    response_status = await client.ping_server(url)
                    assert response_status == status

    @pytest.mark.asyncio
    @pytest.mark.parametrize("url, status, html_content, expectation", [
        ("https://example.com", 200, "<html><body>Test Page</body></html>", does_not_raise()),
        ("https://example.com", 500, "", pytest.raises(ValueError)),
    ])
    async def test_fetch_page_content(self, url, status, html_content, expectation):
        with aioresponses() as m:
            m.get(url, status=status, body=html_content)
            async with HttpClient() as client:
                with expectation:
                    content = await client.fetch_page_content(url)
                    assert content == html_content
