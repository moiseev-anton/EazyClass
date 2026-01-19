import pytest
import requests
from unittest import mock

from scheduler.fetched_data_sync.utils import fetch_page_content


def test_fetch_page_content_success():
    url = "https://example.com"
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.content = b"<html>OK</html>"
    mock_response.raise_for_status.return_value = None

    with mock.patch("scheduler.tasks.scraping.utils.requests.get", return_value=mock_response) as mock_get:
        content = fetch_page_content(url)
        assert content == b"<html>OK</html>"
        mock_get.assert_called_once_with(url, timeout=10)


def test_fetch_page_content_http_error():
    url = "https://example.com/404"
    mock_response = mock.Mock()
    mock_response.raise_for_status.side_effect = requests.HTTPError()

    with mock.patch("scheduler.tasks.scraping.utils.requests.get", return_value=mock_response):
        with pytest.raises(requests.HTTPError):
            fetch_page_content(url)


def test_fetch_page_content_connection_error():
    url = "https://example.com/error"
    with mock.patch("scheduler.tasks.scraping.utils.requests.get", side_effect=requests.RequestException):
        with pytest.raises(requests.RequestException):
            fetch_page_content(url)
