"""Normalization, scoring, dedup and merge helpers for research items."""

from __future__ import annotations

import logging
import math
import re
from datetime import datetime
from typing import Any
from difflib import SequenceMatcher

from core.embedding import EmbeddingError, embed_texts, is_embedding_configured

from agent.ps_agent.models import ResearchItem

from .schemas import MATCH_TEXT_MAX_CHARS

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[A-Za-z0-9]+|[\u4e00-\u9fff]+")


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


async def rank_feed_articles(
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


def normalize_feed_articles(
    articles: list[dict], *, is_patch: bool = False
) -> list[ResearchItem]:
    items: list[ResearchItem] = []
    filtered_no_summary = 0

    for article in articles:
        url = str(article.get("url", "") or "").strip()
        title = str(article.get("title", "") or "").strip()
        published_at = _article_published_at(article)
        summary = str(article.get("summary", "") or "").strip()
        content = str(article.get("content", "") or "").strip()
        article_id = str(article.get("id", "") or "").strip()

        # 过滤：剔除没有 summary 的文章
        if not summary:
            filtered_no_summary += 1
            continue

        items.append(
            ResearchItem(
                id=article_id or url or title,
                title=title,
                url=url,
                source="feed",
                published_at=published_at,
                summary=summary,
                content=content,
                tags=[],
                is_patch=is_patch,
                relevance=0.0,
                quality=0.0,
                novelty=0.0,
            )
        )

    if filtered_no_summary > 0:
        logger.info(
            "[_normalize_feed_articles] Filtered %d articles without summary",
            filtered_no_summary,
        )

    return items


def normalize_web_results(
    results: list[dict], *, is_patch: bool = False
) -> list[ResearchItem]:
    items: list[ResearchItem] = []
    filtered_no_summary = 0

    for result in results:
        url = str(result.get("url", "") or "").strip()
        title = str(result.get("title", "") or "").strip()
        snippet = str(result.get("content", "") or "").strip()
        raw_content = str(result.get("raw_content", "") or "").strip()
        published_at = str(result.get("published_at", "") or "").strip()

        # 过滤：剔除没有 snippet/summary 的文章
        # snippet 是搜索结果的摘要，raw_content 是可选的全文
        if not snippet:
            filtered_no_summary += 1
            continue

        # 如果有 raw_content（Tavily 返回的全文），直接使用它作为 content
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
                tags=["has_full_content"] if has_full_content else [],
                is_patch=is_patch,
                relevance=0.0,
                quality=0.0,
                novelty=0.0,
            )
        )

    if filtered_no_summary > 0:
        logger.info(
            "[_normalize_web_results] Filtered %d results without summary",
            filtered_no_summary,
        )

    return items


def normalize_memories(memories: list[Any]) -> list[ResearchItem]:
    """将 search_memory 返回的记忆列表转为 ResearchItem。

    期望每个 memory 为 dict 或具 __dict__ 的对象，字段：
    id (int/str), topic, reasoning, content；可选 created_at。
    """
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

        items.append(
            ResearchItem(
                id=memory_id,
                title=topic or "历史记忆",
                url="",
                source="memory",
                published_at=published_at,
                summary=str(data.get("reasoning", "") or ""),
                content=content,
                tags=["memory"],
                relevance=0.0,
                quality=0.0,
                novelty=0.0,
            )
        )
    return items


def article_index_key(article: dict) -> str:
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


def dedupe_feed_articles(articles: list[dict]) -> tuple[list[dict], int]:
    if not articles:
        return [], 0

    merged: dict[str, dict] = {}
    dropped = 0
    for article in articles:
        key = article_index_key(article)
        prev = merged.get(key)
        if not prev:
            merged[key] = article
            continue

        dropped += 1
        if _should_take_article(article, prev):
            merged[key] = article

    return list(merged.values()), dropped


def filter_seen_articles(
    articles: list[dict], seen_items: list[ResearchItem]
) -> tuple[list[dict], int]:
    if not articles or not seen_items:
        return articles, 0

    seen_keys = {index_key(item) for item in seen_items}
    filtered: list[dict] = []
    dropped = 0
    for article in articles:
        key = article_index_key(article)
        if key in seen_keys:
            dropped += 1
            continue
        filtered.append(article)
        seen_keys.add(key)

    return filtered, dropped


def index_key(item: ResearchItem) -> str:
    url = str(item.get("url", "") or "").strip().lower()
    if url:
        return f"url::{url}"
    title = str(item.get("title", "") or "").strip().lower()
    if title:
        return f"title::{title}"
    return f"id::{str(item.get('id', ''))}"


def merge_items(
    existing: list[ResearchItem], new_items: list[ResearchItem]
) -> list[ResearchItem]:
    """Merge with light dedup, preferring richer content and higher score."""
    merged: dict[str, ResearchItem] = {
        (index_key(item)): dict(item) for item in existing
    }

    for item in new_items:
        key = index_key(item)
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
