# Scrapy settings for scary_app project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html


BOT_NAME = "scrapy_app"

SPIDER_MODULES = ["scrapy_app.spiders"]
NEWSPIDER_MODULE = "scrapy_app.spiders"



# Obey robots.txt rules
ROBOTSTXT_OBEY = True

# Configure maximum concurrent requests performed by Scrapy (default: 16)
CONCURRENT_REQUESTS = 8

# Configure a delay for requests for the same website (default: 0)
# See https://docs.scrapy.org/en/latest/topics/settings.html#download-delay
# See also autothrottle settings and docs
DOWNLOAD_DELAY = 0.5
RANDOMIZE_DOWNLOAD_DELAY = True
# The download delay setting will honor only one of:
CONCURRENT_REQUESTS_PER_DOMAIN = 4
CONCURRENT_REQUESTS_PER_IP = 4

# Disable cookies (enabled by default)
COOKIES_ENABLED = False


# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = (
    "EazyClassBot/1.0 "
    "(+https://eazyclass.ru; contact: moucee13@gmail.com) "
    "Scrapy/2.14"
)

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-language": "ru,ru-RU;q=0.9,en-US;q=0.8,en;q=0.7,uk;q=0.6",
    }


# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
AUTOTHROTTLE_ENABLED = True
# The initial download delay
AUTOTHROTTLE_START_DELAY = 2.0
# The maximum download delay to be set in case of high latencies
AUTOTHROTTLE_MAX_DELAY = 60.0
# The average number of requests Scrapy should be sending in parallel to
# each remote server
AUTOTHROTTLE_TARGET_CONCURRENCY = 3.0
# Enable showing throttling stats for every response received:
AUTOTHROTTLE_DEBUG = True

# Кэширование DNS для ускорения повторных запросов к тем же доменам.
DNSCACHE_ENABLED = True

# Set settings whose default value is deprecated to a future-proof value
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
FEED_EXPORT_ENCODING = "utf-8"

RETRY_ENABLED = True
DOWNLOAD_TIMEOUT = 10
RETRY_TIMES = 2  # Количество повторных попыток
RETRY_HTTP_CODES = [500, 502, 503, 504, 522, 524, 408, 429]  # HTTP-коды, при которых будет повтор
CLOSESPIDER_ERRORCOUNT = 20   # количество ошибок после которых паук остановится

LOG_ENABLED = True
LOG_LEVEL = "INFO"
LOG_CONFIG = None
LOG_STDOUT = True


# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
# HTTPCACHE_ENABLED = True
#HTTPCACHE_EXPIRATION_SECS = 0
#HTTPCACHE_DIR = "httpcache"
#HTTPCACHE_IGNORE_HTTP_CODES = []
#HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"


# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
# SPIDER_MIDDLEWARES = {
#    "scrapy_app.middlewares.EazyScrapySpiderMiddleware": 543,
# }

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
DOWNLOADER_MIDDLEWARES = {
   "scrapy_app.middlewares.EazyScrapyDownloaderMiddleware": 543,
}


# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
#EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
#}

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
#ITEM_PIPELINES = {
#    "scrapy_app.pipelines.EazyScrapyPipeline": 300,
#}

