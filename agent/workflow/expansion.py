from __future__ import annotations

from agent.models import AgentPlanResult, Article, FocalPoint


def build_expandable_topics(
    plan: AgentPlanResult,
    scored_articles: list[Article],
) -> list[dict]:
    expandable_topics: list[dict] = []
    by_id = {str(article["id"]): article for article in scored_articles}

    for point in plan.get("focal_points", []):
        if point.get("generation_mode") != "OPTIONAL_DEEP":
            continue

        article_ids = [str(article_id) for article_id in point.get("article_ids", [])]
        articles = [by_id[article_id] for article_id in article_ids if article_id in by_id]

        expandable_topics.append(
            {
                "topic": point.get("topic", ""),
                "priority": point.get("priority"),
                "generation_mode": point.get("generation_mode"),
                "brief_summary": point.get("brief_summary", ""),
                "why_expand": point.get("why_expand", ""),
                "match_type": point.get("match_type", ""),
                "reasoning": point.get("reasoning", ""),
                "writing_guide": point.get("writing_guide", ""),
                "article_ids": article_ids,
                "articles": articles,
                "focal_point": point,
            }
        )

    return expandable_topics
