import asyncio
from datetime import datetime, timedelta
import logging
from contextlib import suppress
from typing import Optional
from agent.models import AgentState, RawArticle, StepCallback, log_step
from agent.tools import get_recent_group_update, save_current_execution_records
from agent.tools.constants import DEFAULT_FEED_CANDIDATE_LIMIT
from agent.workflow.executor import AgentExecutor
from agent.workflow.planner import AgentPlanner
from core.llm_client import auto_build_client
from core.models.feed import FeedGroup

logger = logging.getLogger(__name__)


class SummarizeAgenticWorkflow:
    def __init__(self, lazy_init: bool = False):
        """Initialize the agent workflow.

        Args:
            lazy_init: If True, defer AI client initialization until first use.
                      This allows the app to start without API keys configured.
        """
        self._client = None
        self._planner = None
        self._executor = None
        self._states = {}
        
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_stop = asyncio.Event()

        if not lazy_init:
            self._init_client()

    def _init_client(self):
        """Initialize the AI client and pipeline components.

        Raises:
            APIKeyNotConfiguredError: If the API key is not configured.
        """
        if self._client is None:
            self._client = auto_build_client()
            self._planner = AgentPlanner(self._client)
            self._executor = AgentExecutor(self._client)

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
        # This will raise APIKeyNotConfiguredError if API key is not set
        self._init_client()

        groups, articles = await get_recent_group_update(
            hour_gap=hour_gap,
            group_ids=group_ids,
            focus=focus,
            candidate_limit=DEFAULT_FEED_CANDIDATE_LIMIT,
            use_vector_prefilter=True,
        )

        if task_id in self._states:
            raise ValueError(f"Task {task_id} already exists")
        state = self._build_state(groups, articles, focus, on_step)
        self._states[task_id] = state
        n_articles = len(state["raw_articles"])
        n_groups = len(groups)
        logger.info(
            "[workflow] task_id=%s start articles=%d groups=%d focus=%s",
            task_id, n_articles, n_groups, focus or "(empty)",
        )
        try:
            state["status"] = "RUNNING"
            log_step(state, f"🚀 Agent启动，获取到 {n_articles} 篇文章")
            log_step(state, "📋 开始规划阶段...")
            plan = await self.planner.plan(state)
            n_focal = len(plan.get("focal_points", []))
            logger.info(
                "[workflow] task_id=%s plan_done focal_points=%d plan_keys=%s",
                task_id, n_focal, list(plan.keys()) if isinstance(plan, dict) else type(plan).__name__,
            )
            log_step(state, "⚡ 开始执行阶段...")
            results = await self.executor.execute(state)
            result_strings = [result for result, _ in results]
            success_statuses = [success for _, success in results]
            n_ok = sum(success_statuses)
            n_fail = len(results) - n_ok
            logger.info(
                "[workflow] task_id=%s execute_done total=%d success=%d fail=%d",
                task_id, len(results), n_ok, n_fail,
            )
            log_step(state, f"✅ Agent执行完成，共生成 {n_ok} 篇")
            if not results:
                return "", []
            # 使用工具保存执行记录
            await save_current_execution_records(state)

            # 返回简报内容、外部搜索结果和日报概览
            ext_info = state.get("ext_info", [])
            overview = self._extract_overview(plan)
            state["status"] = "COMPLETED"
            expandable_topics = state.get("expandable_topics", [])
            return "\n\n".join(result_strings), ext_info, overview, expandable_topics
        except Exception as e:
            state["status"] = "FAILED"
            logger.exception(
                "[workflow] task_id=%s failed status=%s error=%s",
                task_id, state.get("status"), e,
            )
            raise

    def _extract_overview(self, plan: dict | None) -> str:
        if not plan:
            return ""
        return str(plan.get("today_pattern") or plan.get("daily_overview") or "")

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
        # 收集需要删除的task_id，避免在遍历时修改字典
        tasks_to_remove = []
        for task_id, state in self._states.items():
            if state.get("status") in ("COMPLETED", "FAILED"):
                tasks_to_remove.append(task_id)
            elif state.get("created_at", datetime.now()) < cutoff_time:
                tasks_to_remove.append(task_id)
        # 批量删除
        for task_id in tasks_to_remove:
            del self._states[task_id]

    async def start_cleanup_loop(
        self,
        interval_seconds: int = 300,
        max_age_hours: int = 12,
    ) -> None:
        """启动后台清理协程（只需调用一次）。"""
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
        """停止后台清理协程。"""
        self._cleanup_stop.set()
        if self._cleanup_task:
            # 先等待任务自然结束
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=1.0)
            except asyncio.TimeoutError:
                # 超时则取消任务
                self._cleanup_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._cleanup_task
            self._cleanup_task = None
