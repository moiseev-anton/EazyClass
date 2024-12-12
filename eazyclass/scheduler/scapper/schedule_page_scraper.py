import logging

logger = logging.getLogger(__name__)


class PageScraper:
    def __init__(self, http_client, url, extractor, validator):
        self.client = http_client
        self.url = url
        self.extractor = extractor
        self.validator = validator
        self.scraped_items = []

    async def scrape_page(self):
            try:
                html = await self.client.fetch_page_content(self.url)
                raw_items = self.extractor(html=html).extract()
                if raw_items:
                    for item in raw_items:
                        valid_item = self.validator(item).validate()
                        self.scraped_items.extend(valid_item)
                return self.scraped_items
            except Exception as e:
                logger.error(f"Ошибка при скрапинге страницы {self.url}: {e}")