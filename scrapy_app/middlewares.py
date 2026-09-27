# Define here the models for your spider middleware
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

from scrapy import signals
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# useful for handling different item types with a single interface
from itemadapter import is_item, ItemAdapter


def safe_schedule_url(url):
    """Public schedule endpoint: omit credentials, fragment and unknown query fields."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        return "<non-http URL>"
    hostname = parts.hostname or ""
    if ":" in hostname:
        hostname = f"[{hostname}]"
    host = hostname + (f":{parts.port}" if parts.port else "")
    query = urlencode([(key, value) for key, value in parse_qsl(parts.query)
                       if key == "id" and value.isascii() and value.isdigit() and len(value) <= 32])
    return urlunsplit((parts.scheme, host, parts.path, query, ""))


class EazyScrapySpiderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the spider middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_spider_input(self, response, spider):
        # Called for each response that goes through the spider
        # middleware and into the spider.

        # Should return None or raise an exception.
        return None

    def process_spider_output(self, response, result, spider):
        # Called with the results returned from the Spider, after
        # it has processed the response.

        # Must return an iterable of Request, or item objects.
        for i in result:
            yield i

    def process_spider_exception(self, response, exception, spider):
        # Called when a spider or process_spider_input() method
        # (from other spider middleware) raises an exception.

        # Should return either None or an iterable of Request or item objects.
        pass

    async def process_start(self, start):
        # Called with an async iterator over the spider start() method or the
        # matching method of an earlier spider middleware.
        async for item_or_request in start:
            yield item_or_request

    def spider_opened(self, spider):
        spider.logger.debug("Spider opened: %s" % spider.name)


class EazyScrapyDownloaderMiddleware:
    # Not all methods need to be defined. If a method is not defined,
    # scrapy acts as if the downloader middleware does not modify the
    # passed objects.

    @classmethod
    def from_crawler(cls, crawler):
        # This method is used by Scrapy to create your spiders.
        s = cls()
        crawler.signals.connect(s.spider_opened, signal=signals.spider_opened)
        return s

    def process_request(self, request, spider):
        # Called for each request that goes through the downloader
        # middleware.
        active = getattr(spider.crawler.engine.downloader, 'active', None)
        active_count = len(active) if active is not None else 'unknown'
        request_attempt = request.meta.get("retry_times", 0) + 1
        spider.logger.debug(
            "Отправка запроса %s; попытка %s, активных запросов: %s",
            safe_schedule_url(request.url), request_attempt, active_count,
            extra={"event": "schedule.scrape.request", "group_id": request.meta.get("group_id"),
                   "request_attempt": request_attempt},
        )

        # Must either:
        # - return None: continue processing this request
        # - or return a Response object
        # - or return a Request object
        # - or raise IgnoreRequest: process_exception() methods of
        #   installed downloader middleware will be called
        return None

    def process_response(self, request, response, spider):
        # Called with the response returned from the downloader.

        # Must either;
        # - return a Response object
        # - return a Request object
        # - or raise IgnoreRequest
        return response

    def process_exception(self, request, exception, spider):
        # Called when a download handler or a process_request()
        # (from other downloader middleware) raises an exception.

        # Must either:
        # - return None: continue processing this exception
        # - return a Response object: stops process_exception() chain
        # - return a Request object: stops process_exception() chain
        pass

    def spider_opened(self, spider):
        spider.logger.debug("Spider opened: %s" % spider.name)
