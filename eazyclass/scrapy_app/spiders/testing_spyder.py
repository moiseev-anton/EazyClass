import scrapy
import logging


class TestSpider(scrapy.Spider):
    name = 'test_spider'

    start_urls = ['http://example.com']

    def parse(self, response):
        self.logger.info(f"Title of the page: {response.xpath('//title/text()').get()}")
        logging.info("Test spider completed successfully.")