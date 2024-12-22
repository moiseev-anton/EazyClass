import hashlib

from django.core.cache import caches

cache = caches['scrapy_cache']


class PageCache:
    def __init__(self):
        self.cache = caches['scrapy_cache']

    def get_page_hash(self, url):
        """Получить сохранённый хэш для страницы по её URL."""
        return self.cache.get(f"page_hash:{url}")

    def set_page_hash(self, url, content):
        """Сохранить новый хэш содержимого страницы."""
        hash_value = hashlib.md5(content).hexdigest()
        self.cache.set(f"page_hash:{url}", hash_value)
        return hash_value

    def is_page_changed(self, url, content):
        """Проверить, изменилось ли содержимое страницы."""
        current_hash = hashlib.md5(content).hexdigest()
        stored_hash = self.get_page_hash(url)
        return stored_hash != current_hash
