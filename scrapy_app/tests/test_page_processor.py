import pytest
from scrapy.http import HtmlResponse, Request
from scrapy_app.response_processor import ResponseProcessor
from utils import KeyEnum
from scrapy_app.tests.html_test_cases import html_test_cases
from unittest.mock import MagicMock
import hashlib


@pytest.mark.parametrize(
    "html_body, expected, exception",
    html_test_cases
)
def test_extract_lessons(html_body, expected, exception):

    # Создаем Request с метаданными
    request = Request(url="http://testserver", meta={'group_id': 1})
    # Создаем HtmlResponse и связываем его с Request
    response = HtmlResponse(url='http://testserver', body=html_body, encoding='utf-8', request=request)

    with exception:
        processor = ResponseProcessor(response=response)
        lessons = processor.extract_lessons()
        assert lessons == expected


@pytest.mark.parametrize(
    "old_body, new_body, expected_result",
    [
        # Кейсы:
        (b"<html></html>", b"<html></html>", False),  # Контент не изменился
        (b"<html></html>", b"<html><p>Updated</p></html>", True),  # Контент изменился
        (None, b"<html></html>", True),  # Нет предыдущего хеша
    ],
)
def test_check_content_changed(old_body, new_body, expected_result):
    redis_client = MagicMock()
    redis_client.get.return_value = hashlib.md5(old_body).hexdigest().encode('utf-8') if old_body else None

    # Создаем запрос и ответ для старого тела
    request = Request(url="http://testserver", meta={'group_id': 1})
    response = HtmlResponse(url='http://testserver', body=new_body, encoding='utf-8', request=request)

    # Инициализируем объект ResponseProcessor с новым контентом
    processor = ResponseProcessor(response=response, redis_client=redis_client)

    assert processor.is_content_changed() == expected_result
    redis_client.get.assert_called_with(f"{KeyEnum.PAGE_HASH_PREFIX}1")
