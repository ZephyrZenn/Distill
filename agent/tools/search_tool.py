"""Backward-compatible re-export for workflow search tool now in distill_lib.agent."""

from distill_lib.agent.tools.search_tool import (
    SearchResult,
    fetch_all_contents,
    fetch_web_contents,
    get_search_client,
    is_search_engine_available,
    search,
    search_web,
)

__all__ = [
    "SearchResult",
    "fetch_all_contents",
    "fetch_web_contents",
    "get_search_client",
    "is_search_engine_available",
    "search",
    "search_web",
]
