"""Workflow data/persistence provider interfaces and default adapters."""

from __future__ import annotations

from typing import Protocol

from agent.models import AgentState, RawArticle
from agent.tools import get_recent_group_update, save_current_execution_records
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


class DBWorkflowDataProvider:
    """Default data provider backed by existing DB tool implementation."""

    async def get_recent_group_update(
        self,
        hour_gap: int,
        group_ids: list[int] | None,
        focus: str = "",
    ) -> tuple[list[FeedGroup], list[RawArticle]]:
        return await get_recent_group_update(hour_gap, group_ids or [], focus)


class DBWorkflowPersistenceProvider:
    """Default persistence provider backed by existing DB tool implementation."""

    async def save_current_execution_records(self, state: AgentState) -> None:
        await save_current_execution_records(state)


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
