"""DB-backed workflow providers.

Separated from provider protocols/in-memory providers to keep reusable workflow-lib
paths DB-free by default.
"""

from __future__ import annotations

from importlib import import_module
from typing import Sequence

from agent.models import AgentState, RawArticle, SummaryMemory
from core.models.feed import FeedGroup


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
