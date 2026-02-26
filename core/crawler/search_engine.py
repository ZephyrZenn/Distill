"""Compatibility shim for search engine implementation.

Canonical implementation lives in distill_lib.core.crawler.search_engine.
"""

from distill_lib.core.crawler.search_engine import (
    Any,
    Literal,
    Optional,
    SearchClient,
    SearchResult,
    TavilyClient,
    get_search_client,
    logger,
    logging,
    os,
    search,
)

__all__ = [
    "Any",
    "Literal",
    "Optional",
    "SearchClient",
    "SearchResult",
    "TavilyClient",
    "get_search_client",
    "logger",
    "logging",
    "os",
    "search",
]
