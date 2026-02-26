"""Compatibility shim for search engine implementation.

Canonical implementation lives in distill_lib.core.crawler.search_engine.
"""

from distill_lib.core.crawler.search_engine import (
    SearchClient,
    SearchResult,
    get_search_client,
    search,
)

__all__ = [
    "SearchClient",
    "SearchResult",
    "get_search_client",
    "search",
]
