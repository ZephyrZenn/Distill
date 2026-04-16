from __future__ import annotations

from copy import deepcopy
import re

from agent.models import (
    AgentPlanResult,
    Article,
    ExpandableArticleSnapshot,
    ExpandableTopic,
    FocalPoint,
)
from agent.workflow.layered import OPTIONAL_DEEP, get_optional_deep_points, normalize_plan_layers


def build_expandable_topics(
    plan: AgentPlanResult,
    scored_articles: list[Article],
) -> list[ExpandableTopic]:
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
                topic_id=_topic_id(point),
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


def _topic_id(point: FocalPoint) -> str:
    priority = str(point.get("priority", "topic"))
    slug = re.sub(r"[^a-z0-9]+", "-", point["topic"].lower()).strip("-")
    return f"{priority}-{slug or 'topic'}"


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
