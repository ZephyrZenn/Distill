"""Compatibility shim for crawler implementation.

Canonical implementation lives in distill_lib.core.crawler.crawler.
"""

from distill_lib.core.crawler.crawler import (
    BASE_HEADERS,
    DELAY_BETWEEN_DOMAINS,
    DELAY_BETWEEN_REQUESTS,
    MAX_CONCURRENT_REQUESTS,
    PER_URL_TOTAL_TIMEOUT,
    USER_AGENTS,
    clear_url_cache,
    fetch_all_contents,
    get_content,
    get_headers,
)

__all__ = [
    "BASE_HEADERS",
    "DELAY_BETWEEN_DOMAINS",
    "DELAY_BETWEEN_REQUESTS",
    "MAX_CONCURRENT_REQUESTS",
    "PER_URL_TOTAL_TIMEOUT",
    "USER_AGENTS",
    "clear_url_cache",
    "fetch_all_contents",
    "get_content",
    "get_headers",
]
