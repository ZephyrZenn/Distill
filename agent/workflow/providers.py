"""Workflow data/access/persistence provider interfaces and default adapters."""

from __future__ import annotations

from importlib import import_module
from typing import Protocol, Sequence

from agent.models import AgentState, RawArticle, SummaryMemory
from core.models.feed import FeedGroup


class WorkflowDataProvider(Protocol):
    """Provides workflow input data (groups + articles)."""

    async def get_recent_group_update(
        self,
        hour_gap: int,
        group_ids: list[int] | None,
        focus: str = "",
    ) -> tuple[list[FeedGroup], list[RawArticle]]:
        ...


class WorkflowPersistenceProvider(Protocol):
    """Persists workflow execution records."""

    async def save_current_execution_records(self, state: AgentState) -> None:
        ...


class WorkflowMemoryProvider(Protocol):
    """Loads historical memory records used by planner."""

    async def search_memory(self, queries: Sequence[str]) -> dict[int, SummaryMemory]:
        ...


class WorkflowArticleContentProvider(Protocol):
    """Loads full text for selected article IDs used by executor."""

    async def get_article_content(self, article_ids: list[str]) -> dict[str, str]:
        ...


class DBWorkflowDataProvider:
    """Default data provider backed by existing DB tool implementation."""

    async def get_recent_group_update(
        self,
        hour_gap: int,
        group_ids: list[int] | None,
        focus: str = "",
    ) -> tuple[list[FeedGroup], list[RawArticle]]:
        db_tool = import_module("agent.tools.db_tool")
        return await db_tool.get_recent_group_update(hour_gap, group_ids or [], focus)


class DBWorkflowPersistenceProvider:
    """Default persistence provider backed by existing DB tool implementation."""

    async def save_current_execution_records(self, state: AgentState) -> None:
        memory_tool = import_module("agent.tools.memory_tool")
        await memory_tool.save_current_execution_records(state)


class DBWorkflowMemoryProvider:
    """Default memory provider backed by existing memory tool implementation."""

    async def search_memory(self, queries: Sequence[str]) -> dict[int, SummaryMemory]:
        memory_tool = import_module("agent.tools.memory_tool")
        return await memory_tool.search_memory(queries)


class DBWorkflowArticleContentProvider:
    """Default article-content provider backed by existing DB tool implementation."""

    async def get_article_content(self, article_ids: list[str]) -> dict[str, str]:
        db_tool = import_module("agent.tools.db_tool")
        return await db_tool.get_article_content(article_ids)


class InMemoryWorkflowDataProvider:
    """In-memory provider for DB-free runtime/tests.

    Returns the preloaded data, ignoring runtime query parameters.
    """

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
    """No-op persistence provider for DB-free runtime/tests."""

    async def save_current_execution_records(self, state: AgentState) -> None:
        return None


class InMemoryWorkflowMemoryProvider:
    """In-memory memory provider for DB-free runtime/tests."""

    def __init__(self, memories: dict[int, SummaryMemory] | None = None):
        self.memories = memories or {}

    async def search_memory(self, queries: Sequence[str]) -> dict[int, SummaryMemory]:
        return self.memories


class InMemoryWorkflowArticleContentProvider:
    """In-memory article-content provider for DB-free runtime/tests."""

    def __init__(self, article_contents: dict[str, str] | None = None):
        self.article_contents = article_contents or {}

    async def get_article_content(self, article_ids: list[str]) -> dict[str, str]:
        return {aid: self.article_contents.get(aid, "") for aid in article_ids}
