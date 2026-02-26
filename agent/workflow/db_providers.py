"""DB-backed workflow providers for default agent runtime wiring."""

from __future__ import annotations

from importlib import import_module
from typing import Sequence

from distill_lib.agent.models import AgentState, RawArticle, SummaryMemory
from distill_lib.core.models.feed import FeedGroup


class DBWorkflowDataProvider:
    async def get_recent_group_update(
        self,
        hour_gap: int,
        group_ids: list[int] | None,
        focus: str = "",
    ) -> tuple[list[FeedGroup], list[RawArticle]]:
        db_tool = import_module("agent.tools.db_tool")
        return await db_tool.get_recent_group_update(hour_gap, group_ids or [], focus)


class DBWorkflowPersistenceProvider:
    async def save_current_execution_records(self, state: AgentState) -> None:
        memory_tool = import_module("agent.tools.memory_tool")
        await memory_tool.save_current_execution_records(state)


class DBWorkflowMemoryProvider:
    async def search_memory(self, queries: Sequence[str]) -> dict[int, SummaryMemory]:
        memory_tool = import_module("agent.tools.memory_tool")
        return await memory_tool.search_memory(queries)


class DBWorkflowArticleContentProvider:
    async def get_article_content(self, article_ids: list[str]) -> dict[str, str]:
        db_tool = import_module("agent.tools.db_tool")
        return await db_tool.get_article_content(article_ids)
