"""Tool message payload truncation and JSON serialization helpers."""

from __future__ import annotations

import dataclasses
import json
from datetime import date, datetime
from typing import Any

from .schemas import (
    FEED_SUMMARY_MAX_CHARS,
    TOOL_MESSAGE_MAX_CHARS,
    TOOL_MAX_LIST_ITEMS,
    WEB_RESULT_SNIPPET_MAX_CHARS,
)


def json_default(value: Any) -> str:
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


def _shrink_web_payload(payload: dict) -> dict:
    meta = payload.get("meta", {}) or {}
    results = list(payload.get("results", []) or [])

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

    text = json.dumps(compact, ensure_ascii=False, default=json_default)
    if len(text) <= TOOL_MESSAGE_MAX_CHARS:
        return compact

    while len(compact["results"]) > TOOL_MAX_LIST_ITEMS:
        compact["results"] = compact["results"][:TOOL_MAX_LIST_ITEMS]
        text = json.dumps(compact, ensure_ascii=False, default=json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return compact

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

    text = json.dumps(compact, ensure_ascii=False, default=json_default)
    if len(text) <= TOOL_MESSAGE_MAX_CHARS:
        return compact

    while len(compact["articles"]) > TOOL_MAX_LIST_ITEMS:
        compact["articles"] = compact["articles"][:TOOL_MAX_LIST_ITEMS]
        text = json.dumps(compact, ensure_ascii=False, default=json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return compact

    if len(text) > TOOL_MESSAGE_MAX_CHARS:
        for a in compact["articles"]:
            if isinstance(a, dict):
                a["summary"] = ""
        return compact

    return compact


def truncate_for_tool_message(payload: dict) -> str:
    """Serialize payload for tool-message history, shrinking if needed.

    We prefer producing valid JSON with bounded lists/snippets so the model can
    reliably read `meta` (e.g., the query) and avoid repeating the same search.
    """
    safe_payload: dict = payload
    text = json.dumps(safe_payload, ensure_ascii=False, default=json_default)
    if len(text) <= TOOL_MESSAGE_MAX_CHARS:
        return text

    # First pass: shrink known large payload shapes.
    if isinstance(payload, dict) and "results" in payload:
        safe_payload = _shrink_web_payload(payload)
        text = json.dumps(safe_payload, ensure_ascii=False, default=json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return text

    if isinstance(payload, dict) and "articles" in payload:
        safe_payload = _shrink_feed_payload(payload)
        text = json.dumps(safe_payload, ensure_ascii=False, default=json_default)
        if len(text) <= TOOL_MESSAGE_MAX_CHARS:
            return text

    # Last resort: fall back to a head truncation.
    head = text[: TOOL_MESSAGE_MAX_CHARS - 64]
    return f"{head}...<truncated {len(text) - len(head)} chars>"
