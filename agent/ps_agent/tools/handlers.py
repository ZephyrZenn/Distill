"""Tool execution handlers for search_feeds, search_web and search_memory."""

from __future__ import annotations

import logging
import re
import time

from agent.tools import (
    get_all_feeds,
    get_recent_feed_update,
    is_search_engine_available,
    search_memory as _search_memory,
    search_web as _search_web,
)
from agent.tools.constants import (
    MAX_FEED_CANDIDATE_LIMIT,
    SEARCH_FEEDS_CACHE_TTL_SECONDS,
    SEARCH_FEEDS_CANDIDATE_MIN,
    SEARCH_FEEDS_CANDIDATE_MULTIPLIER,
    SEARCH_FEEDS_DEFAULT_HOUR_GAP,
    SEARCH_FEEDS_DEFAULT_LIMIT,
    SEARCH_FEEDS_FALLBACK_TOPN,
    SEARCH_FEEDS_SCORE_LOG_TOPN,
    SEARCH_MEMORY_DEFAULT_DAYS_AGO,
    SEARCH_MEMORY_DEFAULT_LIMIT,
    SEARCH_MEMORY_MAX_DAYS_AGO,
    SEARCH_MEMORY_MAX_LIMIT,
    SEARCH_MEMORY_MIN_DAYS_AGO,
    SEARCH_MEMORY_MIN_LIMIT,
    SEARCH_WEB_DEFAULT_MAX_RESULTS,
    SEARCH_WEB_PATCH_MAX_RESULTS,
)
from core.embedding import is_embedding_configured

from agent.ps_agent.state import PSAgentState

from .normalize import (
    dedupe_feed_articles,
    filter_seen_articles,
    rank_feed_articles,
    normalize_feed_articles,
)
from .schemas import MIN_MATCH_SCORE, WEB_RESULT_SNIPPET_MAX_CHARS

logger = logging.getLogger(__name__)

_SEARCH_FEEDS_CACHE: dict[str, tuple[float, list, list]] = {}


def _search_feeds_cache_key(feed_ids: list[int], hour_gap: int, query: str) -> str:
    return f"{','.join(str(fid) for fid in sorted(feed_ids))}|{hour_gap}|{query.lower().strip()}"


def _get_cached_feed_search(key: str):
    cached = _SEARCH_FEEDS_CACHE.get(key)
    if not cached:
        return None
    expires_at, feeds, articles = cached
    if expires_at < time.time():
        _SEARCH_FEEDS_CACHE.pop(key, None)
        return None
    return feeds, articles


def _set_cached_feed_search(key: str, feeds: list, articles: list) -> None:
    _SEARCH_FEEDS_CACHE[key] = (
        time.time() + SEARCH_FEEDS_CACHE_TTL_SECONDS,
        feeds,
        articles,
    )


def parse_query_exclusions(query: str) -> tuple[str, list[str]]:
    """Extract exclusion keywords from query string.

    Parses search engine exclusion syntax (-keyword) and separates them
    from the main query. This allows LLMs to use natural search syntax
    while properly routing exclusions to the exclude_keywords parameter.

    Examples:
        "OpenAI GPT-5 -百度 -阿里" -> ("OpenAI GPT-5", ["百度", "阿里"])
        "科技股 AI -A股 -港股" -> ("科技股 AI", ["A股", "港股"])
        "Tech news" -> ("Tech news", [])

    Args:
        query: Raw query string that may contain -keyword exclusions

    Returns:
        Tuple of (cleaned_query, exclusion_keywords_list)
    """
    if not query:
        return "", []

    # Match -keyword or -"multi word" patterns
    exclude_pattern = r'-([^\s"]+)|-"([^"]+)"'
    exclusions = re.findall(exclude_pattern, query)

    exclude_keywords = []
    for single_quote, double_quote in exclusions:
        exclude_keywords.append(single_quote or double_quote)

    # Remove exclusions from query
    clean_query = re.sub(exclude_pattern, "", query).strip()
    clean_query = re.sub(r"\s+", " ", clean_query)

    if exclude_keywords:
        logger.info("[search_feeds] Parsed exclusions from query: %s", exclude_keywords)

    return clean_query, exclude_keywords


async def handle_search_feeds(args: dict, state: PSAgentState) -> dict:
    run_id = state.get("run_id", "-")
    query = str(args.get("query", "") or "").strip()
    hour_gap = int(
        args.get("hour_gap", SEARCH_FEEDS_DEFAULT_HOUR_GAP)
        or SEARCH_FEEDS_DEFAULT_HOUR_GAP
    )
    limit = int(args.get("limit", SEARCH_FEEDS_DEFAULT_LIMIT) or SEARCH_FEEDS_DEFAULT_LIMIT)
    exclude_keywords = args.get("exclude_keywords") or []
    is_patch = bool(args.get("is_patch", False))

    if isinstance(exclude_keywords, str):
        exclude_keywords = [exclude_keywords]

    # Parse exclusions from query (support -keyword syntax)
    parsed_query, query_exclusions = parse_query_exclusions(query)
    query = parsed_query
    exclude_keywords = list(exclude_keywords) + query_exclusions

    feeds = await get_all_feeds()
    if not feeds:
        return {"feeds": [], "articles": []}

    feed_ids = [feed.id for feed in feeds]
    candidate_limit = (
        max(
            SEARCH_FEEDS_CANDIDATE_MIN,
            min(MAX_FEED_CANDIDATE_LIMIT, limit * SEARCH_FEEDS_CANDIDATE_MULTIPLIER),
        )
        if query
        else 0
    )
    cache_key = _search_feeds_cache_key(feed_ids, hour_gap, query)
    cached_result = _get_cached_feed_search(cache_key)
    if cached_result:
        feeds_result, articles = cached_result
    else:
        feeds_result, articles = await get_recent_feed_update(
            hour_gap,
            feed_ids,
            query=query,
            candidate_limit=candidate_limit,
            use_vector_prefilter=True,
        )
        _set_cached_feed_search(cache_key, feeds_result, articles)

    articles, in_call_deduped = dedupe_feed_articles(articles)

    # Apply Exclusion Filter (P1 Feature)
    if exclude_keywords:
        kept_articles = []
        for art in articles:
            text = (
                str(art.get("title", "")) + " " + str(art.get("summary", ""))
            ).lower()
            if not any(k.lower() in text for k in exclude_keywords):
                kept_articles.append(art)

        logger.info(
            "[tool:search_feeds] Exclusion filter dropped %d items (keywords=%s)",
            len(articles) - len(kept_articles),
            exclude_keywords,
        )
        articles = kept_articles

    if query:
        logger.info(
            "[tool:search_feeds] run_id=%s query=%s hour_gap=%s candidates=%d embedding=%s",
            run_id,
            query,
            hour_gap,
            len(articles),
            is_embedding_configured(),
        )
        scored = await rank_feed_articles(articles, query)
        filtered = [article for score, article in scored if score >= MIN_MATCH_SCORE]
        if not filtered:
            fallback_count = min(SEARCH_FEEDS_FALLBACK_TOPN, len(scored))
            filtered = [article for _, article in scored[:fallback_count]]
        articles = filtered
        logger.info(
            "[tool:search_feeds] run_id=%s kept=%d top_scores=%s",
            run_id,
            len(articles),
            ",".join(
                str(a.get("match_score", 0.0))
                for a in articles[:SEARCH_FEEDS_SCORE_LOG_TOPN]
            ),
        )

    history_deduped = 0
    if state.get("research_items"):
        articles, history_deduped = filter_seen_articles(
            articles, state.get("research_items", [])
        )

    if limit > 0:
        articles = articles[:limit]

    return {
        "meta": {
            "query": query,
            "hour_gap": hour_gap,
            "count": len(articles),
            "deduped": {
                "within_call": in_call_deduped,
                "history": history_deduped,
            },
        },
        "feeds": [f.__dict__ for f in feeds_result],
        "articles": normalize_feed_articles(articles, is_patch=is_patch),
    }


async def handle_search_web(args: dict, _state: PSAgentState) -> dict:
    if not is_search_engine_available():
        logger.warning("搜索引擎不可用，search_web 返回空结果")
        return {"results": [], "meta": {"available": False}}

    query = str(args.get("query", "") or "").strip()
    if not query:
        raise ValueError("search_web 的 query 不能为空")

    time_range = str(args.get("time_range", "day") or "day")
    max_results = int(
        args.get("max_results", SEARCH_WEB_DEFAULT_MAX_RESULTS)
        or SEARCH_WEB_DEFAULT_MAX_RESULTS
    )
    topic = str(args.get("topic", "news") or "news")
    exclude_keywords = args.get("exclude_keywords") or []
    is_patch = bool(args.get("is_patch", False))

    if isinstance(exclude_keywords, str):
        exclude_keywords = [exclude_keywords]

    include_raw_content = is_patch
    actual_max_results = (
        min(max_results, SEARCH_WEB_PATCH_MAX_RESULTS)
        if is_patch
        else max_results + len(exclude_keywords)
    )

    results = await _search_web(
        query,
        time_range=time_range,
        max_results=actual_max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )
    normalized = [r.__dict__ if hasattr(r, "__dict__") else dict(r) for r in results]

    # Apply Exclusion Filter (P1 Feature)
    if exclude_keywords:
        kept_results = []
        for res in normalized:
            text = (
                str(res.get("title", "")) + " " + str(res.get("content", ""))
            ).lower()
            if not any(k.lower() in text for k in exclude_keywords):
                kept_results.append(res)
        normalized = kept_results[:max_results]
    else:
        normalized = normalized[:max_results]

    # 截断过长的摘要
    for row in normalized:
        content = str(row.get("content", "") or "").strip()
        if len(content) > WEB_RESULT_SNIPPET_MAX_CHARS:
            row["content"] = content[:WEB_RESULT_SNIPPET_MAX_CHARS] + "..."

    logger.info(
        "[tool:search_web] query=%s count=%d",
        query,
        len(normalized),
    )

    return {
        "meta": {
            "query": query,
            "time_range": time_range,
            "count": len(normalized),
        },
        "results": normalized,
    }


async def handle_search_memory(args: dict, _state: PSAgentState) -> dict:
    """搜索历史记忆中的背景材料与趋势上下文。"""
    keywords = args.get("keywords") or []
    if isinstance(keywords, str):
        keywords = [keywords]
    keywords = [str(k).strip() for k in keywords if k and str(k).strip()]
    if not keywords:
        return {
            "memories": [],
            "meta": {
                "keywords": [],
                "days_ago": 0,
                "count": 0,
                "message": "keywords 不能为空",
            },
        }

    days_ago = int(
        args.get("days_ago", SEARCH_MEMORY_DEFAULT_DAYS_AGO)
        or SEARCH_MEMORY_DEFAULT_DAYS_AGO
    )
    days_ago = max(SEARCH_MEMORY_MIN_DAYS_AGO, min(SEARCH_MEMORY_MAX_DAYS_AGO, days_ago))
    limit = int(args.get("limit", SEARCH_MEMORY_DEFAULT_LIMIT) or SEARCH_MEMORY_DEFAULT_LIMIT)
    limit = max(SEARCH_MEMORY_MIN_LIMIT, min(SEARCH_MEMORY_MAX_LIMIT, limit))

    try:
        result = await _search_memory(
            queries=keywords,
            days_ago=days_ago,
            limit=limit,
        )
    except ValueError as exc:
        logger.warning("[tool:search_memory] %s", exc)
        return {
            "memories": [],
            "meta": {
                "keywords": keywords,
                "days_ago": days_ago,
                "count": 0,
                "error": str(exc),
            },
        }

    # result 是 dict[int, SummaryMemory]，转为 list 供下游 normalize_memories 使用
    memories_list = list(result.values())
    # SummaryMemory 是 TypedDict，转为普通 dict 并保证可序列化
    memories_payload = []
    for m in memories_list:
        if hasattr(m, "get"):
            memories_payload.append(dict(m))
        elif hasattr(m, "__dict__"):
            memories_payload.append(m.__dict__)
        else:
            memories_payload.append({"content": str(m)})

    logger.info(
        "[tool:search_memory] keywords=%s days_ago=%s count=%d",
        keywords[:5],
        days_ago,
        len(memories_payload),
    )

    return {
        "meta": {
            "keywords": keywords,
            "days_ago": days_ago,
            "count": len(memories_payload),
        },
        "memories": memories_payload,
    }
