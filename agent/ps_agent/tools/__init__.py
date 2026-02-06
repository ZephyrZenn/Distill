"""Tool schemas and execution helpers for the agentic LangGraph workflow.

This module does three jobs:
1. Define tool *schemas* for model-side function calling.
2. Execute tool calls coming back from the model.
3. Normalize and deduplicate research items so later stages are stable.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import math
import re
import time
from difflib import SequenceMatcher
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Callable, Coroutine, Literal

from agent.tools import (
    fetch_web_contents,
    get_all_feeds,
    get_article_content,
    get_recent_feed_update,
    is_search_engine_available,
    search_memory as _search_memory,
    search_web as _search_web,
)
from agent.utils import extract_json, get_query_embedding
from core.embedding import EmbeddingError, embed_texts, is_embedding_configured
from core.models.llm import FunctionDefinition, Message, Tool, ToolCall

from agent.ps_agent.state import PSAgentState
from agent.ps_agent.models import ResearchItem, DiscardedItem

logger = logging.getLogger(__name__)

ToolHandler = Callable[[dict, PSAgentState], Coroutine[Any, Any, dict]]

# Keep tool message payloads bounded so the conversation does not explode.
TOOL_MESSAGE_MAX_CHARS = 10_000
MATCH_TEXT_MAX_CHARS = 800
MIN_MATCH_SCORE = 0.18

# When a tool payload is too large, we shrink it (instead of truncating raw JSON)
# so the model still gets stable structure + meta (query/count/etc).
WEB_RESULT_SNIPPET_MAX_CHARS = 450
# 放宽 feed / 写作阶段的内容截断，避免证据过早被丢弃
FEED_SUMMARY_MAX_CHARS = 1_200
AUTO_FETCH_WEB_MAX_ITEMS = 6
FETCHED_CONTENT_MAX_CHARS = 1_200
TOOL_MAX_LIST_ITEMS = 12

_WORD_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class RegisteredTool:
    """A tool entry with both schema and executor."""

    schema: Tool
    handler: ToolHandler


def build_tool_schemas(*, current_date: str) -> list[Tool]:
    """Build model-facing tool definitions.

    We thread `current_date` into descriptions to strongly bias toward "today".
    """
    recency_hint = (
        f"今天是 {current_date}。除非明确需要背景信息，请优先检索 24 小时内的内容。"
    )

    return [
        Tool(
            function=FunctionDefinition(
                name="search_feeds",
                description=(
                    "从系统内的 RSS 订阅源检索相关文章。"
                    "返回标题、链接、摘要、发布时间等元信息。"
                    f"{recency_hint}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "检索关键词，可为空表示广泛扫描。支持 -关键词 排除语法（如 'OpenAI -百度'）",
                        },
                        "hour_gap": {
                            "type": "integer",
                            "description": "时间窗口（小时），建议 24 或更小。",
                            "default": 24,
                            "minimum": 1,
                            "maximum": 168,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回的最大文章数量。",
                            "default": 30,
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "exclude_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "排除包含这些关键词的文章。",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            )
        ),
        Tool(
            function=FunctionDefinition(
                name="finish_research",
                description=(
                    "当你已经拥有足够证据可以开始写报告时调用。"
                    "请用结构化方式提交关键发现与不确定点，系统会切换到写作阶段。"
                    f"{recency_hint}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "key_findings": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键发现要点（建议 1-3 条）。",
                        },
                        "open_questions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "仍不确定/需要继续跟踪的点（可为空）。",
                        },
                        "notes": {
                            "type": "string",
                            "description": "可选补充说明。",
                        },
                    },
                    "required": ["key_findings"],
                    "additionalProperties": False,
                },
            )
        ),
        Tool(
            function=FunctionDefinition(
                name="search_web",
                description=(
                    "在互联网上搜索最新信息，返回搜索结果的摘要/片段（而非全文）。"
                    "适合用于补充订阅源未覆盖的实时信息。若需要正文，请再调用 fetch_content。"
                    f"{recency_hint}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "具体、可执行的搜索查询语句。",
                        },
                        "time_range": {
                            "type": "string",
                            "enum": ["day", "week", "month", "year"],
                            "description": '时间范围限制。做"当日重点"时应优先 day。',
                            "default": "day",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "希望返回的最大结果数。",
                            "default": 8,
                            "minimum": 1,
                            "maximum": 20,
                        },
                        "topic": {
                            "type": "string",
                            "enum": ["news", "finance"],
                            "description": (
                                "搜索类别："
                                "'news' 用于实时新闻（政治、体育、重大时事）；"
                                "'finance' 用于金融相关；"
                            ),
                            "default": "news",
                        },
                        "exclude_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "排除包含这些关键词的结果。",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            )
        ),
        Tool(
            function=FunctionDefinition(
                name="search_memory",
                description=(
                    "搜索历史记忆中的背景材料与趋势上下文。"
                    "用于补充解释性背景，而不是替代当日信息。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键词列表，建议 2-6 个。",
                        },
                        "days_ago": {
                            "type": "integer",
                            "description": "回溯天数，默认 14 天。",
                            "default": 14,
                            "minimum": 1,
                            "maximum": 365,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量上限。",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                    },
                    "required": ["keywords"],
                    "additionalProperties": False,
                },
            )
        ),
        Tool(
            function=FunctionDefinition(
                name="fetch_content",
                description=(
                    "按文章 ID 或 URL 抓取更完整的正文内容。"
                    "当摘要不足以支撑结论时使用。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "article_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "RSS 文章 ID 列表。",
                        },
                        "urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "网页 URL 列表。",
                        },
                        "max_items": {
                            "type": "integer",
                            "description": "最多抓取多少项以控制成本。",
                            "default": 8,
                            "minimum": 1,
                            "maximum": 30,
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            )
        ),
    ]


# ---------------------------------------------------------------------------
# Tool handlers (real execution)
# ---------------------------------------------------------------------------


def _parse_query_exclusions(query: str) -> tuple[str, list[str]]:
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
    import re

    if not query:
        return "", []

    # Match -keyword or -"multi word" patterns
    # Pattern explanation:
    #   -([^\s"]+)  matches -keyword (single word)
    #   -"([^"]+)"   matches -"multi word phrase"
    exclude_pattern = r'-([^\s"]+)|-"([^"]+)"'
    exclusions = re.findall(exclude_pattern, query)

    exclude_keywords = []
    for single_quote, double_quote in exclusions:
        exclude_keywords.append(single_quote or double_quote)

    # Remove exclusions from query
    clean_query = re.sub(exclude_pattern, '', query).strip()
    # Normalize whitespace (collapse multiple spaces)
    clean_query = re.sub(r'\s+', ' ', clean_query)

    if exclude_keywords:
        logger.info(
            f"[search_feeds] Parsed exclusions from query: {exclude_keywords}"
        )

    return clean_query, exclude_keywords


async def _handle_search_feeds(args: dict, state: PSAgentState) -> dict:
    run_id = state.get("run_id", "-")
    query = str(args.get("query", "") or "").strip()
    hour_gap = int(args.get("hour_gap", 24) or 24)
    limit = int(args.get("limit", 30) or 30)
    exclude_keywords = args.get("exclude_keywords") or []
    is_patch = bool(args.get("is_patch", False))

    if isinstance(exclude_keywords, str):
        exclude_keywords = [exclude_keywords]

    # NEW: Parse exclusions from query (support -keyword syntax)
    parsed_query, query_exclusions = _parse_query_exclusions(query)
    query = parsed_query
    exclude_keywords = list(exclude_keywords) + query_exclusions

    feeds = await get_all_feeds()
    if not feeds:
        return {"feeds": [], "articles": []}

    feed_ids = [feed.id for feed in feeds]
    feeds_result, articles = await get_recent_feed_update(hour_gap, feed_ids)

    articles, in_call_deduped = _dedupe_feed_articles(articles)

    # Apply Exclusion Filter (P1 Feature)
    if exclude_keywords:
        kept_articles = []
        for art in articles:
            # Check title and summary
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
        scored = await _rank_feed_articles(articles, query)
        filtered = [article for score, article in scored if score >= MIN_MATCH_SCORE]
        if not filtered:
            fallback_count = min(8, len(scored))
            filtered = [article for _, article in scored[:fallback_count]]
        articles = filtered
        logger.info(
            "[tool:search_feeds] run_id=%s kept=%d top_scores=%s",
            run_id,
            len(articles),
            ",".join(str(a.get("match_score", 0.0)) for a in articles[:5]),
        )

    history_deduped = 0
    if state.get("research_items"):
        articles, history_deduped = _filter_seen_articles(
            articles, state.get("research_items", [])
        )

    if limit > 0:
        articles = articles[:limit]

    # Keep meta first so even if a downstream logger/prompt truncates,
    # the model still sees query/count/dedup info.
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
        "articles": _normalize_feed_articles(articles, is_patch=is_patch),
    }


async def _handle_finish_research(
    args: dict, state: PSAgentState
) -> dict:  # noqa: ARG001
    key_findings = args.get("key_findings") or []
    open_questions = args.get("open_questions") or []
    notes = str(args.get("notes", "") or "").strip()

    if not isinstance(key_findings, list) or not key_findings:
        raise ValueError("finish_research.key_findings 必须是非空列表")

    key_findings = [str(x).strip() for x in key_findings if str(x).strip()]
    open_questions = [str(x).strip() for x in open_questions if str(x).strip()]

    return {
        "meta": {
            "ok": True,
            "count_findings": len(key_findings),
            "count_open": len(open_questions),
        },
        "key_findings": key_findings,
        "open_questions": open_questions,
        "notes": notes,
    }


async def _handle_search_web(args: dict, state: PSAgentState) -> dict:
    if not is_search_engine_available():
        logger.warning("搜索引擎不可用，search_web 返回空结果")
        return {"results": [], "meta": {"available": False}}

    query = str(args.get("query", "") or "").strip()
    if not query:
        raise ValueError("search_web 的 query 不能为空")

    time_range = str(args.get("time_range", "day") or "day")
    max_results = int(args.get("max_results", 8) or 8)
    topic = str(args.get("topic", "news") or "news")
    exclude_keywords = args.get("exclude_keywords") or []
    is_patch = bool(args.get("is_patch", False))

    if isinstance(exclude_keywords, str):
        exclude_keywords = [exclude_keywords]

    # For web search, we can try to add negative prompt to query if supported,
    # but doing post-filtering is safer and engine-agnostic.
    # Patch 搜索启用 include_raw_content 直接获取全文，避免后续 fetch_content 调用
    # 对于补丁搜索，限制结果数量以控制成本
    include_raw_content = is_patch
    actual_max_results = min(max_results, 5) if is_patch else max_results + len(exclude_keywords)

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


async def _handle_search_memory(args: dict, state: PSAgentState) -> dict:
    keywords = args.get("keywords", [])
    if not isinstance(keywords, list) or not keywords:
        raise ValueError("search_memory 的 keywords 必须是非空列表")

    keywords = [str(k).strip() for k in keywords if str(k).strip()]
    days_ago = int(args.get("days_ago", 14) or 14)
    limit = int(args.get("limit", 10) or 10)

    memories = await _search_memory(keywords, days_ago=days_ago, limit=limit)

    # Convert mapping -> list for easier prompting downstream.
    memory_list = list(memories.values()) if isinstance(memories, dict) else memories

    return {
        "memories": memory_list,
        "meta": {"keywords": keywords, "days_ago": days_ago, "count": len(memory_list)},
    }


async def _handle_fetch_content(args: dict, state: PSAgentState) -> dict:
    article_ids = args.get("article_ids") or []
    urls = args.get("urls") or []
    max_items = int(args.get("max_items", 8) or 8)

    if max_items > 0:
        article_ids = list(article_ids)[:max_items]
        urls = list(urls)[:max_items]

    result: dict[str, Any] = {}

    if article_ids:
        result["article_contents"] = await get_article_content(article_ids)

    if urls:
        result["web_contents"] = await fetch_web_contents(urls)

    result["meta"] = {
        "article_ids": article_ids,
        "urls": urls,
        "count": len(article_ids) + len(urls),
    }
    return result


# ---------------------------------------------------------------------------
# Normalization and merging helpers
# ---------------------------------------------------------------------------


def _safe_parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _article_published_at(article: dict) -> str:
    value = article.get("published_at")
    if value is None:
        value = article.get("pub_date")
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "").strip()


def _published_timestamp(value: str | datetime | None) -> float:
    if isinstance(value, datetime):
        return value.timestamp()
    dt = _safe_parse_dt(str(value or ""))
    if not dt:
        return 0.0
    return dt.timestamp()


def _recency_bonus(published_at: str | None, *, now: datetime) -> float:
    dt = _safe_parse_dt(published_at)
    if not dt:
        return 0.0
    now_ref = datetime.now(dt.tzinfo) if dt.tzinfo else now
    if dt.tzinfo is None and now_ref.tzinfo is not None:
        dt = dt.replace(tzinfo=now_ref.tzinfo)
    delta_hours = (now_ref - dt).total_seconds() / 3600
    if delta_hours <= 24:
        return 0.6
    if delta_hours <= 72:
        return 0.3
    return 0.0


def _compute_score(
    *,
    source: str,
    published_at: str | None,
    match_score: float = 0.0,
    extra: float = 0.0,
    now: datetime,
) -> float:
    """统一的评分函数：基础分 + 时效加成 + 匹配度 + 额外权重。"""
    base = _base_score_for_source(source)
    return (
        base
        + _recency_bonus(published_at, now=now)
        + float(match_score or 0.0)
        + float(extra or 0.0)
    )


def _base_score_for_source(source: str) -> float:
    if source == "feed":
        return 1.0
    if source == "web":
        return 0.8
    if source == "memory":
        return 0.5
    return 0.4


def _normalize_for_match(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokenize(text: str) -> list[str]:
    if not text:
        return []
    normalized = _normalize_for_match(text)
    tokens: list[str] = []
    for part in _WORD_RE.findall(normalized):
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if len(part) == 1:
                tokens.append(part)
            elif len(part) == 2:
                tokens.append(part)
            else:
                tokens.extend(part[i : i + 2] for i in range(len(part) - 1))
        else:
            tokens.append(part)
    return tokens


def _lexical_score(query: str, text: str) -> float:
    query_tokens = _tokenize(query)
    if not query_tokens:
        return 0.0
    text_tokens = _tokenize(text)
    if not text_tokens:
        return 0.0
    text_set = set(text_tokens)
    overlap = sum(1 for token in query_tokens if token in text_set)
    return overlap / max(len(query_tokens), 1)


def _fuzzy_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _semantic_scores(query: str, texts: list[str]) -> list[float]:
    if not texts:
        return []
    if not is_embedding_configured():
        return [0.0] * len(texts)
    try:
        embeddings = await embed_texts([query] + texts)
    except EmbeddingError as exc:
        logger.warning("Embedding 不可用，跳过语义匹配: %s", exc)
        return [0.0] * len(texts)

    query_vec = embeddings[0]
    scores: list[float] = []
    for vec in embeddings[1:]:
        score = _cosine_similarity(query_vec, vec)
        scores.append(max(score, 0.0))
    return scores


def _combine_match_scores(
    lexical: float, fuzzy: float, semantic: float, *, use_semantic: bool
) -> float:
    if use_semantic:
        return 0.5 * lexical + 0.2 * fuzzy + 0.3 * semantic
    return 0.7 * lexical + 0.3 * fuzzy


def _build_match_text(article: dict) -> str:
    title = str(article.get("title", "") or "").strip()
    summary = str(article.get("summary", "") or "").strip()
    text = f"{title}\n{summary}".strip() if summary else title
    return text[:MATCH_TEXT_MAX_CHARS]


async def _rank_feed_articles(
    articles: list[dict], query: str
) -> list[tuple[float, dict]]:
    if not articles:
        return []

    match_texts = [_build_match_text(article) for article in articles]
    semantic_scores = await _semantic_scores(query, match_texts)
    use_semantic = any(score > 0 for score in semantic_scores)
    norm_query = _normalize_for_match(query)

    scored: list[tuple[float, dict]] = []
    for idx, article in enumerate(articles):
        title = str(article.get("title", "") or "").strip()
        summary = str(article.get("summary", "") or "").strip()
        match_text = match_texts[idx]

        lexical = _lexical_score(query, match_text)
        fuzzy = max(
            _fuzzy_ratio(query, title),
            _fuzzy_ratio(query, summary[:200]),
        )
        semantic = semantic_scores[idx] if idx < len(semantic_scores) else 0.0
        score = _combine_match_scores(
            lexical, fuzzy, semantic, use_semantic=use_semantic
        )

        if norm_query and norm_query in _normalize_for_match(match_text):
            score += 0.15

        score = min(score, 1.0)
        scored.append((score, {**article, "match_score": round(score, 4)}))

    scored.sort(
        key=lambda item: (
            item[0],
            _published_timestamp(_article_published_at(item[1])),
        ),
        reverse=True,
    )
    return scored


def _normalize_feed_articles(
    articles: list[dict], *, is_patch: bool = False
) -> list[ResearchItem]:
    now = datetime.now()
    items: list[ResearchItem] = []
    filtered_no_summary = 0

    for article in articles:
        url = str(article.get("url", "") or "").strip()
        title = str(article.get("title", "") or "").strip()
        published_at = _article_published_at(article)
        summary = str(article.get("summary", "") or "").strip()
        content = str(article.get("content", "") or "").strip()
        article_id = str(article.get("id", "") or "").strip()
        match_score = float(article.get("match_score", 0.0) or 0.0)

        # 过滤：剔除没有 summary 的文章
        if not summary:
            filtered_no_summary += 1
            continue

        score = _compute_score(
            source="feed",
            published_at=published_at,
            match_score=match_score * 0.6,
            now=now,
        )

        items.append(
            ResearchItem(
                id=article_id or url or title,
                title=title,
                url=url,
                source="feed",
                published_at=published_at,
                summary=summary,
                content=content,
                score=score,
                tags=[],
                is_patch=is_patch,
                relevance=0.0,
                freshness=0.0,
                quality=0.0,
                novelty=0.0,
            )
        )

    if filtered_no_summary > 0:
        logger.info(
            "[_normalize_feed_articles] Filtered %d articles without summary",
            filtered_no_summary
        )

    return items


def _normalize_web_results(
    results: list[dict], *, is_patch: bool = False, time_range: str = "week"
) -> list[ResearchItem]:
    now = datetime.now()
    items: list[ResearchItem] = []
    filtered_no_summary = 0

    for result in results:
        url = str(result.get("url", "") or "").strip()
        title = str(result.get("title", "") or "").strip()
        snippet = str(result.get("content", "") or "").strip()
        raw_content = str(result.get("raw_content", "") or "").strip()
        published_at = str(result.get("published_at", "") or "").strip()
        score_val = float(result.get("score", 0.0) or 0.0)

        # 过滤：剔除没有 snippet/summary 的文章
        # snippet 是搜索结果的摘要，raw_content 是可选的全文
        if not snippet:
            filtered_no_summary += 1
            continue

        score = _compute_score(
            source="web",
            published_at=published_at,
            match_score=score_val,
            now=now,
        )

        # 如果有 raw_content（Tavily 返回的全文），直接使用它作为 content
        # 这样就不需要后续调用 fetch_content 来抓取网页
        has_full_content = raw_content and len(raw_content) > 100

        items.append(
            ResearchItem(
                id=url or title,
                title=title,
                url=url,
                source="web",
                published_at=published_at,
                summary=snippet,
                content=raw_content if has_full_content else "",
                score=score,
                tags=["has_full_content"] if has_full_content else [],
                is_patch=is_patch,
                relevance=0.0,
                freshness=0.0,
                quality=0.0,
                novelty=0.0,
                time_range_hint=time_range,  # Store search time range for freshness fallback
            )
        )

    if filtered_no_summary > 0:
        logger.info(
            "[_normalize_web_results] Filtered %d results without summary",
            filtered_no_summary
        )

    return items


def _normalize_memories(memories: list[Any]) -> list[ResearchItem]:
    now = datetime.now()
    items: list[ResearchItem] = []
    for memory in memories:
        if hasattr(memory, "__dict__"):
            data = dict(memory.__dict__)
        elif isinstance(memory, dict):
            data = memory
        else:
            data = {"content": str(memory)}

        topic = str(data.get("topic", "") or "").strip()
        content = str(data.get("content", "") or "").strip()
        memory_id = str(data.get("id", "") or topic or content[:32])
        published_at = str(data.get("created_at", "") or "").strip()

        score = _compute_score(
            source="memory",
            published_at=published_at,
            match_score=0.0,
            now=now,
        )

        items.append(
            ResearchItem(
                id=memory_id,
                title=topic or "历史记忆",
                url="",
                source="memory",
                published_at=published_at,
                summary=str(data.get("reasoning", "") or ""),
                content=content,
                score=score,
                tags=["memory"],
                relevance=0.0,
                freshness=0.0,
                quality=0.0,
                novelty=0.0,
            )
        )
    return items


def _article_index_key(article: dict) -> str:
    url = str(article.get("url", "") or article.get("link", "") or "").strip().lower()
    if url:
        return f"url::{url}"
    title = str(article.get("title", "") or "").strip().lower()
    if title:
        return f"title::{title}"
    return f"id::{str(article.get('id', ''))}"


def _should_take_article(candidate: dict, previous: dict) -> bool:
    cand_pub = _published_timestamp(_article_published_at(candidate))
    prev_pub = _published_timestamp(_article_published_at(previous))
    if cand_pub != prev_pub:
        return cand_pub > prev_pub

    cand_summary = len(str(candidate.get("summary", "") or ""))
    prev_summary = len(str(previous.get("summary", "") or ""))
    if cand_summary != prev_summary:
        return cand_summary > prev_summary

    cand_title = len(str(candidate.get("title", "") or ""))
    prev_title = len(str(previous.get("title", "") or ""))
    return cand_title > prev_title


def _dedupe_feed_articles(articles: list[dict]) -> tuple[list[dict], int]:
    if not articles:
        return [], 0

    merged: dict[str, dict] = {}
    dropped = 0
    for article in articles:
        key = _article_index_key(article)
        prev = merged.get(key)
        if not prev:
            merged[key] = article
            continue

        dropped += 1
        if _should_take_article(article, prev):
            merged[key] = article

    return list(merged.values()), dropped


def _filter_seen_articles(
    articles: list[dict], seen_items: list[ResearchItem]
) -> tuple[list[dict], int]:
    if not articles or not seen_items:
        return articles, 0

    seen_keys = {_index_key(item) for item in seen_items}
    filtered: list[dict] = []
    dropped = 0
    for article in articles:
        key = _article_index_key(article)
        if key in seen_keys:
            dropped += 1
            continue
        filtered.append(article)
        seen_keys.add(key)

    return filtered, dropped


def _index_key(item: ResearchItem) -> str:
    url = str(item.get("url", "") or "").strip().lower()
    if url:
        return f"url::{url}"
    title = str(item.get("title", "") or "").strip().lower()
    if title:
        return f"title::{title}"
    return f"id::{str(item.get('id', ''))}"


def _merge_items(
    existing: list[ResearchItem], new_items: list[ResearchItem]
) -> list[ResearchItem]:
    """Merge with light dedup, preferring richer content and higher score."""
    merged: dict[str, ResearchItem] = {
        (_index_key(item)): dict(item) for item in existing
    }

    for item in new_items:
        key = _index_key(item)
        prev = merged.get(key)
        if not prev:
            merged[key] = dict(item)
            continue

        prev_content = str(prev.get("content", "") or "")
        new_content = str(item.get("content", "") or "")

        # Prefer the item with richer content or higher score.
        take_new = len(new_content) > len(prev_content) or float(
            item.get("score", 0.0) or 0.0
        ) > float(prev.get("score", 0.0) or 0.0)

        if take_new:
            merged[key] = dict(item)
        else:
            # Keep existing but bump score slightly to reflect repeated evidence.
            prev_score = float(prev.get("score", 0.0) or 0.0)
            merged[key]["score"] = round(prev_score + 0.05, 4)

    # Return as a stable, ranked list.
    ranked = sorted(
        merged.values(),
        key=lambda x: float(x.get("score", 0.0) or 0.0),
        reverse=True,
    )
    return [ResearchItem(**item) for item in ranked]


def _merge_fetch_content(
    existing: list[ResearchItem], payload: dict
) -> list[ResearchItem]:
    article_contents = payload.get("article_contents", {}) or {}
    web_contents = payload.get("web_contents", {}) or {}

    if not article_contents and not web_contents:
        return existing

    updated: list[ResearchItem] = []
    article_lookup = {str(k): str(v) for k, v in article_contents.items()}
    web_lookup = {str(k): str(v) for k, v in web_contents.items()}

    for item in existing:
        new_item = dict(item)
        item_id = str(item.get("id", "") or "")
        item_url = str(item.get("url", "") or "")

        if item_id and item_id in article_lookup:
            new_item["content"] = article_lookup[item_id]
        elif item_url and item_url in web_lookup:
            new_item["content"] = web_lookup[item_url]

        updated.append(ResearchItem(**new_item))

    return updated


async def _auto_fetch_fulltext_for_web_items(
    research_items: list[ResearchItem],
    *,
    max_items: int = AUTO_FETCH_WEB_MAX_ITEMS,
    summary_max_chars: int = FETCHED_CONTENT_MAX_CHARS,
) -> tuple[list[ResearchItem], dict]:
    """
    自动为高分 web 结果抓取少量正文并做截断，返回更新后的 items 和 meta。
    """
    candidates = [
        item
        for item in research_items
        if item.get("source") == "web" and not item.get("content")
    ]
    if not candidates:
        return research_items, {"auto_fetch": 0}

    candidates = sorted(
        candidates,
        key=lambda i: (
            float(i.get("score", 0.0) or 0.0),
            _published_timestamp(i.get("published_at")),
        ),
        reverse=True,
    )[:max_items]

    urls = [i.get("url") for i in candidates if i.get("url")]
    if not urls:
        return research_items, {"auto_fetch": 0}

    contents = await fetch_web_contents(urls)
    updated: list[ResearchItem] = []
    fetched_count = 0
    for item in research_items:
        if item in candidates:
            url = item.get("url")
            if url and url in contents and contents[url]:
                text = str(contents[url])
                if len(text) > summary_max_chars:
                    text = text[:summary_max_chars] + "..."
                new_item = dict(item)
                new_item["content"] = text
                updated.append(ResearchItem(**new_item))
                fetched_count += 1
                continue
        updated.append(item)

    return updated, {"auto_fetch": fetched_count}


def _truncate_for_tool_message(payload: dict) -> str:
    """Serialize payload for tool-message history, shrinking if needed.

    We prefer producing valid JSON with bounded lists/snippets so the model can
    reliably read `meta` (e.g., the query) and avoid repeating the same search.
    """
    safe_payload: dict = payload
    text = json.dumps(safe_payload, ensure_ascii=False, default=_json_default)
    if len(text) <= TOOL_MESSAGE_MAX_CHARS:
        return text

    # First pass: shrink known large payload shapes.
    if isinstance(payload, dict) and "results" in payload:
        safe_payload = _shrink_web_payload(payload)
        text = json.dumps(safe_payload, ensure_ascii=False, default=_json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return text

    if isinstance(payload, dict) and "articles" in payload:
        safe_payload = _shrink_feed_payload(payload)
        text = json.dumps(safe_payload, ensure_ascii=False, default=_json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return text

    # Last resort: fall back to a head truncation.
    head = text[: TOOL_MESSAGE_MAX_CHARS - 64]
    return f"{head}...<truncated {len(text) - len(head)} chars>"


def _shrink_web_payload(payload: dict) -> dict:
    meta = payload.get("meta", {}) or {}
    results = list(payload.get("results", []) or [])

    # Keep meta first so it's visible even if a caller truncates.
    compact: dict[str, Any] = {"meta": meta, "results": []}

    for row in results:
        if not isinstance(row, dict):
            compact["results"].append({"title": str(row)})
            continue
        content = str(row.get("content", "") or "").strip()
        if len(content) > WEB_RESULT_SNIPPET_MAX_CHARS:
            content = content[:WEB_RESULT_SNIPPET_MAX_CHARS] + "..."
        compact["results"].append(
            {
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                "content": content,
                "score": row.get("score", 0.0),
                **(
                    {"published_at": row.get("published_at", "")}
                    if "published_at" in row
                    else {}
                ),
            }
        )

    # Reduce list size if needed.
    text = json.dumps(compact, ensure_ascii=False, default=_json_default)
    if len(text) <= TOOL_MESSAGE_MAX_CHARS:
        return compact

    while len(compact["results"]) > TOOL_MAX_LIST_ITEMS:
        compact["results"] = compact["results"][:TOOL_MAX_LIST_ITEMS]
        text = json.dumps(compact, ensure_ascii=False, default=_json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return compact

    # If still too large, drop content fields.
    if len(text) > TOOL_MESSAGE_MAX_CHARS:
        for r in compact["results"]:
            if isinstance(r, dict):
                r["content"] = ""
        return compact

    return compact


def _shrink_feed_payload(payload: dict) -> dict:
    meta = payload.get("meta", {}) or {}
    feeds = payload.get("feeds", []) or []
    articles = list(payload.get("articles", []) or [])

    compact: dict[str, Any] = {"meta": meta, "feeds": feeds, "articles": []}

    for row in articles:
        if not isinstance(row, dict):
            compact["articles"].append({"title": str(row)})
            continue
        summary = str(row.get("summary", "") or "").strip()
        if len(summary) > FEED_SUMMARY_MAX_CHARS:
            summary = summary[:FEED_SUMMARY_MAX_CHARS] + "..."
        compact["articles"].append(
            {
                "id": row.get("id", ""),
                "title": row.get("title", ""),
                "url": row.get("url", ""),
                "summary": summary,
                "pub_date": row.get("pub_date", ""),
                **(
                    {"match_score": row.get("match_score", 0.0)}
                    if "match_score" in row
                    else {}
                ),
            }
        )

    text = json.dumps(compact, ensure_ascii=False, default=_json_default)
    if len(text) <= TOOL_MESSAGE_MAX_CHARS:
        return compact

    while len(compact["articles"]) > TOOL_MAX_LIST_ITEMS:
        compact["articles"] = compact["articles"][:TOOL_MAX_LIST_ITEMS]
        text = json.dumps(compact, ensure_ascii=False, default=_json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return compact

    if len(text) > TOOL_MESSAGE_MAX_CHARS:
        for a in compact["articles"]:
            if isinstance(a, dict):
                a["summary"] = ""
        return compact

    return compact


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return str(value)


def _parse_arguments(arguments: str) -> dict:
    if not arguments:
        return {}
    try:
        return json.loads(arguments, strict=False)
    except json.JSONDecodeError:
        # Fall back to our robust extractor.
        return extract_json(arguments)


def _push_recent_query(recent: list[str], query: str, *, limit: int = 6) -> list[str]:
    query = str(query or "").strip()
    if not query:
        return recent
    updated = list(recent or [])
    # Avoid consecutive duplicates.
    if updated and updated[-1] == query:
        return updated[-limit:]
    updated.append(query)
    return updated[-limit:]


def _tool_registry(current_date: str) -> dict[str, RegisteredTool]:
    schemas = build_tool_schemas(current_date=current_date)
    schema_by_name = {tool.function.name: tool for tool in schemas}

    return {
        "search_feeds": RegisteredTool(
            schema=schema_by_name["search_feeds"], handler=_handle_search_feeds
        ),
        "finish_research": RegisteredTool(
            schema=schema_by_name["finish_research"], handler=_handle_finish_research
        ),
        "search_web": RegisteredTool(
            schema=schema_by_name["search_web"], handler=_handle_search_web
        ),
        "search_memory": RegisteredTool(
            schema=schema_by_name["search_memory"], handler=_handle_search_memory
        ),
        "fetch_content": RegisteredTool(
            schema=schema_by_name["fetch_content"], handler=_handle_fetch_content
        ),
    }


def get_registered_tools(*, current_date: str) -> list[Tool]:
    """Public helper: model-facing tool schemas."""
    registry = _tool_registry(current_date)
    return [entry.schema for entry in registry.values()]


def get_researcher_tools(*, current_date: str) -> list[Tool]:
    """Get tools for the researcher node (search_feeds and search_web only).

    The researcher only needs to plan searches, not execute fetch_content or
    search_memory. finish_research is signaled by returning no tool calls.
    """
    registry = _tool_registry(current_date)
    return [registry["search_feeds"].schema, registry["search_web"].schema]


async def execute_tool_calls(state: PSAgentState, tool_calls: list[ToolCall]) -> dict:
    """Execute tool calls and return state updates.

    This function is intentionally "thick" so the rest of the graph stays simple.
    """
    if not tool_calls:
        return {}

    run_id = state.get("run_id", "-")
    log_history: list[str] = []

    def _emit(message: str) -> None:
        log_history.append(message)
        callback = state.get("on_step")
        if callback:
            try:
                callback(message)
            except Exception:
                pass

    registry = _tool_registry(state["current_date"])

    messages: list[Message] = []
    research_items = list(state.get("research_items", []))
    recent_web_queries = list(state.get("recent_web_queries", []) or [])

    # P1: Initialize query_history for spiral collection
    query_history = list(state.get("query_history", []) or [])

    for call in tool_calls:
        entry = registry.get(call.name)
        if not entry:
            logger.warning("未知工具: %s", call.name)
            tool_payload = {"error": f"unknown tool: {call.name}"}
            messages.append(
                Message.tool(
                    content=json.dumps(tool_payload, ensure_ascii=False),
                    name=call.name,
                    tool_call_id=call.id,
                )
            )
            continue

        args = _parse_arguments(call.arguments)

        # AUTO: Add is_patch=True for search tools in PATCH_MODE
        # This is managed by the system, not set by LLM
        if state.get("execution_mode") == "PATCH_MODE" and call.name in ("search_feeds", "search_web"):
            args["is_patch"] = True

        _emit(f"🔧 tool: {call.name} args={json.dumps(args, ensure_ascii=False)[:240]}")
        logger.info(
            "[tool] run_id=%s name=%s call_id=%s args=%s",
            run_id,
            call.name,
            call.id,
            json.dumps(args, ensure_ascii=False)[:800],
        )
        try:
            payload = await entry.handler(args, state)
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("工具执行失败: %s", call.name)
            payload = {"error": str(exc), "tool": call.name, "args": args}

        meta = payload.get("meta") if isinstance(payload, dict) else None
        try:
            payload_chars = len(
                json.dumps(payload, ensure_ascii=False, default=_json_default)
            )
        except Exception:
            payload_chars = -1
        logger.info(
            "[tool] run_id=%s name=%s ok=%s payload_chars=%d meta=%s",
            run_id,
            call.name,
            "error" not in payload,
            payload_chars,
            json.dumps(meta, ensure_ascii=False)[:400] if meta is not None else "",
        )
        if isinstance(meta, dict):
            _emit(
                f"🔧 tool: {call.name} meta={json.dumps(meta, ensure_ascii=False)[:240]}"
            )

        # Update tool message history.
        messages.append(
            Message.tool(
                content=_truncate_for_tool_message(payload),
                name=call.name,
                tool_call_id=call.id,
            )
        )

        # Normalize research additions.
        if call.name == "search_feeds":
            articles = payload.get("articles", []) or []
            new_items = _normalize_feed_articles(articles)
            research_items = _merge_items(research_items, new_items)
        elif call.name == "search_web":
            query_text = str(args.get("query", "") or "")
            recent_web_queries = _push_recent_query(
                recent_web_queries, query_text
            )
            results = payload.get("results", []) or []

            # P1: Record query to query_history with embedding
            
                # query_embedding = await get_query_embedding(query_text)
            # TODO: 需要重新添加 embedding
            query_history.append({
                "query": query_text,
                "timestamp": time.time(),
                "results_count": len(results),
            })
            logger.info(
                f"[tool] Recorded query to history: '{query_text[:50]}...' "
                f"results={len(results)}"
            )
            new_items = _normalize_web_results(results, is_patch=bool(args.get("is_patch", False)))
            research_items = _merge_items(research_items, new_items)
            # Patch 搜索模式（include_raw_content=True）已获取全文，跳过 auto-fetch
            # Tavily 返回 raw_content 后无需再用 httpx 抓取
            # is_patch = bool(args.get("is_patch", False))
            # if not is_patch:
            #     # 自动抓取少量高分 web 结果正文，截断后写回 content
            #     research_items, auto_meta = await _auto_fetch_fulltext_for_web_items(
            #         research_items,
            #         max_items=AUTO_FETCH_WEB_MAX_ITEMS,
            #         summary_max_chars=FETCHED_CONTENT_MAX_CHARS,
            #     )
            #     if auto_meta.get("auto_fetch"):
            #         _emit(f"🔧 tool: auto fetch content {auto_meta['auto_fetch']} items")
        elif call.name == "search_memory":
            memories = payload.get("memories", []) or []
            new_items = _normalize_memories(memories)
            research_items = _merge_items(research_items, new_items)
        elif call.name == "fetch_content":
            research_items = _merge_fetch_content(research_items, payload)

        logger.info(
            "[tool] run_id=%s after=%s research_items=%d",
            run_id,
            call.name,
            len(research_items),
        )
        _emit(
            f"🔧 tool: after {call.name} research_items={len(research_items)}"
        )


    return {
        "log_history": log_history,
        "messages": messages,
        "recent_web_queries": recent_web_queries,
        "research_items": research_items,
        "query_history": query_history,  # P1: Query history with embeddings
        "tool_call_count": state.get("tool_call_count", 0) + len(tool_calls),
        "status": "researching",
        "last_error": None,
    }


__all__ = [
    "execute_tool_calls",
    "get_registered_tools",
    "get_researcher_tools",
]
