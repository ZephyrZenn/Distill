"""Workflow provider interfaces and DB-free in-memory adapters."""

from __future__ import annotations

from typing import Protocol, Sequence

from agent.models import AgentState, RawArticle, SummaryMemory
from core.models.feed import FeedGroup


class WorkflowDataProvider(Protocol):
    async def get_recent_group_update(
        self,
        hour_gap: int,
        group_ids: list[int] | None,
        focus: str = "",
    ) -> tuple[list[FeedGroup], list[RawArticle]]:
        ...


class WorkflowPersistenceProvider(Protocol):
    async def save_current_execution_records(self, state: AgentState) -> None:
        ...


class WorkflowMemoryProvider(Protocol):
    async def search_memory(self, queries: Sequence[str]) -> dict[int, SummaryMemory]:
        ...


class WorkflowArticleContentProvider(Protocol):
    async def get_article_content(self, article_ids: list[str]) -> dict[str, str]:
        ...


class InMemoryWorkflowDataProvider:
    def __init__(
        self,
        groups: list[FeedGroup] | None = None,
        articles: list[RawArticle] | None = None,
    ):
        self.groups = groups or []
        self.articles = articles or []

    async def get_recent_group_update(
        self,
        hour_gap: int,
        group_ids: list[int] | None,
        focus: str = "",
    ) -> tuple[list[FeedGroup], list[RawArticle]]:
        return self.groups, self.articles


class NoopWorkflowPersistenceProvider:
    async def save_current_execution_records(self, state: AgentState) -> None:
        return None


class InMemoryWorkflowMemoryProvider:
    def __init__(self, memories: dict[int, SummaryMemory] | None = None):
        self.memories = memories or {}

    async def search_memory(self, queries: Sequence[str]) -> dict[int, SummaryMemory]:
        return self.memories


class InMemoryWorkflowArticleContentProvider:
    def __init__(self, article_contents: dict[str, str] | None = None):
        self.article_contents = article_contents or {}

    async def get_article_content(self, article_ids: list[str]) -> dict[str, str]:
        return {aid: self.article_contents.get(aid, "") for aid in article_ids}


__all__ = [
    "WorkflowDataProvider",
    "WorkflowPersistenceProvider",
    "WorkflowMemoryProvider",
    "WorkflowArticleContentProvider",
    "InMemoryWorkflowDataProvider",
    "InMemoryWorkflowMemoryProvider",
    "InMemoryWorkflowArticleContentProvider",
    "NoopWorkflowPersistenceProvider",
]
