from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re

from agent.models import (
    AgentPlanResult,
    AgentState,
    Article,
    ExpandableArticleSnapshot,
    ExpandableTopic,
    FocalPoint,
    SummaryMemory,
)
from agent.workflow.layered import OPTIONAL_DEEP, get_optional_deep_points, normalize_plan_layers


def build_expandable_topics(
    plan: AgentPlanResult,
    scored_articles: list[Article],
) -> list[ExpandableTopic]:
    source_priority_by_signature = _source_priority_by_signature(plan)
    source_priority_by_topic = _source_priority_by_topic(plan)
    normalized_plan = normalize_plan_layers(plan)
    articles_by_id = {str(article["id"]): article for article in scored_articles}
    topics: list[ExpandableTopic] = []

    for point in get_optional_deep_points(normalized_plan):
        snapshots = [
            _article_snapshot(articles_by_id[article_id])
            for article_id in point.get("article_ids", [])
            if article_id in articles_by_id
        ]
        if not snapshots:
            continue
        topics.append(
            ExpandableTopic(
                topic_id=_topic_id(
                    point,
                    source_priority_by_signature,
                    source_priority_by_topic,
                ),
                topic=point["topic"],
                why_expand=str(point.get("why_expand", "")),
                strategy=point["strategy"],
                search_query=str(point.get("search_query", "")),
                history_memory_id=list(point.get("history_memory_id", [])),
                focal_point={**deepcopy(point), "generation_mode": OPTIONAL_DEEP},
                articles=snapshots,
            )
        )

    return topics


def _topic_id(
    point: FocalPoint,
    source_priority_by_signature: dict[tuple[str, tuple[str, ...]], int],
    source_priority_by_topic: dict[str, int],
) -> str:
    signature = _point_signature(point)
    priority = source_priority_by_signature.get(signature)
    if priority is None:
        priority = source_priority_by_topic.get(point["topic"])
    if priority is None:
        priority = point.get("priority", "topic")
    priority = str(priority)
    slug = re.sub(r"[^a-z0-9]+", "-", point["topic"].lower()).strip("-")
    return f"{priority}-{slug or 'topic'}"


def _source_priority_by_signature(plan: AgentPlanResult) -> dict[tuple[str, tuple[str, ...]], int]:
    priorities: dict[tuple[str, tuple[str, ...]], int] = {}
    for point in plan.get("focal_points", []):
        if not isinstance(point, dict):
            continue
        priority = point.get("priority")
        if isinstance(priority, bool) or not isinstance(priority, int):
            continue
        priorities.setdefault(_point_signature(point), priority)
    return priorities


def _source_priority_by_topic(plan: AgentPlanResult) -> dict[str, int]:
    priorities: dict[str, int] = {}
    for point in plan.get("focal_points", []):
        if not isinstance(point, dict):
            continue
        priority = point.get("priority")
        topic = point.get("topic")
        if not isinstance(topic, str):
            continue
        if isinstance(priority, bool) or not isinstance(priority, int):
            continue
        priorities.setdefault(topic, priority)
    return priorities


def _point_signature(point: FocalPoint) -> tuple[str, tuple[str, ...]]:
    article_ids = tuple(str(article_id) for article_id in point.get("article_ids", []))
    return point["topic"], article_ids


def _article_snapshot(article: Article) -> ExpandableArticleSnapshot:
    return ExpandableArticleSnapshot(
        id=str(article.get("id", "")),
        title=str(article.get("title", "")),
        url=str(article.get("url", "")),
        summary=str(article.get("summary", "")),
        pub_date=str(article.get("pub_date", "")),
        score=float(article.get("score", 0.0) or 0.0),
        reasoning=str(article.get("reasoning", "")),
    )


def build_expansion_state(
    topic: ExpandableTopic,
    history_memories: dict[int, SummaryMemory] | None = None,
) -> AgentState:
    focal_point = topic["focal_point"]
    articles = [
        {
            "id": article["id"],
            "title": article["title"],
            "url": article["url"],
            "summary": article["summary"],
            "pub_date": article["pub_date"],
            "score": article["score"],
            "reasoning": article["reasoning"],
        }
        for article in topic["articles"]
    ]
    return AgentState(
        focus="",
        groups=[],
        raw_articles=[],
        scored_articles=articles,
        plan={
            "daily_overview": "",
            "today_pattern": "",
            "daily_brief_items": [],
            "focal_points": [focal_point],
            "discarded_items": [],
        },
        history_memories=history_memories or {},
        log_history=[],
        status="RUNNING",
        created_at=datetime.now(),
    )
