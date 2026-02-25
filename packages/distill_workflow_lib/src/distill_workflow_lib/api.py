from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agent.models import RawArticle
from distill_workflow_lib.executor import AgentExecutor
from distill_workflow_lib.planner import AgentPlanner
from distill_workflow_lib.providers import (
    InMemoryWorkflowArticleContentProvider,
    InMemoryWorkflowDataProvider,
    InMemoryWorkflowMemoryProvider,
    NoopWorkflowPersistenceProvider,
)
from distill_workflow_lib.workflow import SummarizeAgenticWorkflow
from core.llm_client import auto_build_client
from core.models.feed import Feed, FeedArticle, FeedGroup
from core.parsers import parse_feed, parse_opml


@dataclass
class WorkflowRunResult:
    summary: str
    ext_info: list[dict]
    logs: list[str]
    article_count: int


def _feed_articles_to_raw_articles(feed_articles: dict[str, list[FeedArticle]]) -> list[RawArticle]:
    articles: list[RawArticle] = []
    for _, item_list in feed_articles.items():
        for item in item_list:
            articles.append(
                RawArticle(
                    id=str(item.id),
                    title=item.title,
                    url=item.url,
                    summary=item.summary,
                    pub_date=item.pub_date,
                    content=item.content or "",
                )
            )
    return articles


async def run_workflow_from_opml(
    opml_text: str,
    focus: str = "",
    hour_gap: int = 24,
) -> WorkflowRunResult:
    feeds: list[Feed] = parse_opml(opml_text)
    feed_articles = parse_feed(feeds)
    articles = _feed_articles_to_raw_articles(feed_articles)
    groups = [FeedGroup(id=1, title="Imported OPML", desc="workflow-lib", feeds=feeds)]
    return await run_workflow_from_articles(
        articles=articles,
        focus=focus,
        hour_gap=hour_gap,
        groups=groups,
    )


async def run_workflow_from_articles(
    articles: list[RawArticle],
    focus: str = "",
    hour_gap: int = 24,
    groups: list[FeedGroup] | None = None,
) -> WorkflowRunResult:
    groups = groups or [FeedGroup(id=1, title="Input", desc="workflow-lib")]
    article_contents = {
        str(article["id"]): article.get("content", "") for article in articles if article.get("content")
    }

    workflow = SummarizeAgenticWorkflow(
        lazy_init=True,
        data_provider=InMemoryWorkflowDataProvider(groups=groups, articles=articles),
        persistence_provider=NoopWorkflowPersistenceProvider(),
        memory_provider=InMemoryWorkflowMemoryProvider(memories={}),
        article_content_provider=InMemoryWorkflowArticleContentProvider(
            article_contents=article_contents
        ),
    )

    client = auto_build_client()
    workflow._init_client = lambda: None  # type: ignore[method-assign]
    workflow._planner = AgentPlanner(client, memory_provider=workflow._memory_provider)
    workflow._executor = AgentExecutor(
        client, article_content_provider=workflow._article_content_provider
    )

    task_id = f"workflow-lib-{datetime.now().timestamp()}"
    summary, ext_info = await workflow.summarize(
        task_id=task_id,
        hour_gap=hour_gap,
        group_ids=[group.id for group in groups],
        focus=focus,
    )

    state = workflow._states.get(task_id, {})
    return WorkflowRunResult(
        summary=summary,
        ext_info=ext_info,
        logs=state.get("log_history", []),
        article_count=len(articles),
    )
