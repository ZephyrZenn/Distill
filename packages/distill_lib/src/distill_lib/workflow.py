import asyncio
from datetime import datetime, timedelta
import logging
from contextlib import suppress
from typing import Optional
from agent.models import AgentState, RawArticle, StepCallback, log_step
from distill_lib.executor import AgentExecutor
from distill_lib.planner import AgentPlanner
from agent.workflow.db_providers import (
    DBWorkflowArticleContentProvider,
    DBWorkflowDataProvider,
    DBWorkflowMemoryProvider,
    DBWorkflowPersistenceProvider,
)
from distill_lib.providers import (
    WorkflowArticleContentProvider,
    WorkflowDataProvider,
    WorkflowMemoryProvider,
    WorkflowPersistenceProvider,
)
from core.llm_client import auto_build_client
from core.models.feed import FeedGroup

logger = logging.getLogger(__name__)


class SummarizeAgenticWorkflow:
    def __init__(
        self,
        lazy_init: bool = False,
        data_provider: WorkflowDataProvider | None = None,
        persistence_provider: WorkflowPersistenceProvider | None = None,
        memory_provider: WorkflowMemoryProvider | None = None,
        article_content_provider: WorkflowArticleContentProvider | None = None,
    ):
        self._client = None
        self._planner = None
        self._executor = None
        self._states = {}
        self._data_provider = data_provider or DBWorkflowDataProvider()
        self._persistence_provider = (
            persistence_provider or DBWorkflowPersistenceProvider()
        )
        self._memory_provider = memory_provider or DBWorkflowMemoryProvider()
        self._article_content_provider = (
            article_content_provider or DBWorkflowArticleContentProvider()
        )

        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_stop = asyncio.Event()

        if not lazy_init:
            self._init_client()

    def _init_client(self):
        if self._client is None:
            self._client = auto_build_client()
            self._planner = AgentPlanner(
                self._client,
                memory_provider=self._memory_provider,
            )
            self._executor = AgentExecutor(
                self._client,
                article_content_provider=self._article_content_provider,
            )

    @property
    def planner(self) -> AgentPlanner:
        self._init_client()
        return self._planner

    @property
    def executor(self) -> AgentExecutor:
        self._init_client()
        return self._executor

    async def summarize(
        self,
        task_id: str,
        hour_gap: int,
        group_ids: Optional[list[int]],
        focus: str = "",
        on_step: Optional[StepCallback] = None,
    ):
        self._init_client()

        groups, articles = await self._data_provider.get_recent_group_update(
            hour_gap, group_ids, focus
        )

        if task_id in self._states:
            raise ValueError(f"Task {task_id} already exists")
        state = self._build_state(groups, articles, focus, on_step)
        self._states[task_id] = state
        try:
            state["status"] = "RUNNING"
            log_step(state, f"🚀 Agent启动，获取到 {len(state['raw_articles'])} 篇文章")
            log_step(state, "📋 开始规划阶段...")
            plan = await self.planner.plan(state)
            logger.info("Plan: %s", plan)
            log_step(state, "⚡ 开始执行阶段...")
            results = await self.executor.execute(state)
            logger.info("Results: %s", results)
            result_strings = [result for result, _ in results]
            success_statuses = [success for _, success in results]
            log_step(state, f"✅ Agent执行完成，共生成 {sum(success_statuses)} 篇")
            if not results:
                return "", []
            await self._persistence_provider.save_current_execution_records(state)

            ext_info = state.get("ext_info", [])
            state["status"] = "COMPLETED"
            return "\n\n".join(result_strings), ext_info
        except Exception as e:
            state["status"] = "FAILED"
            logger.exception("Task %s failed: %s", task_id, e)
            raise

    def _build_state(
        self,
        groups: list[FeedGroup],
        articles: list[RawArticle],
        focus: str = "",
        on_step: Optional[StepCallback] = None,
    ) -> AgentState:
        state = AgentState(
            groups=groups,
            raw_articles=articles,
            log_history=[],
            focus=focus,
            created_at=datetime.now(),
            status="PENDING",
        )
        if on_step:
            state["on_step"] = on_step
        return state

    def clean_completed_tasks(self, max_age_hours: int = 12):
        now = datetime.now()
        cutoff_time = now - timedelta(hours=max_age_hours)
        tasks_to_remove = []
        for task_id, state in self._states.items():
            if state.get("status") in ("COMPLETED", "FAILED"):
                tasks_to_remove.append(task_id)
            elif state.get("created_at", datetime.now()) < cutoff_time:
                tasks_to_remove.append(task_id)
        for task_id in tasks_to_remove:
            del self._states[task_id]

    async def start_cleanup_loop(
        self,
        interval_seconds: int = 300,
        max_age_hours: int = 12,
    ) -> None:
        if self._cleanup_task and not self._cleanup_task.done():
            return

        self._cleanup_stop.clear()

        async def _loop():
            try:
                while not self._cleanup_stop.is_set():
                    self.clean_completed_tasks(max_age_hours=max_age_hours)
                    await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                pass

        self._cleanup_task = asyncio.create_task(_loop())

    async def stop_cleanup_loop(self) -> None:
        self._cleanup_stop.set()
        if self._cleanup_task:
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=1.0)
            except asyncio.TimeoutError:
                self._cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._cleanup_task
            self._cleanup_task = None
