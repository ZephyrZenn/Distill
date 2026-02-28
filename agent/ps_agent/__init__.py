"""Agentic daily-research agent built on LangGraph.

This module exposes a single high-level entrypoint: PlanSolveAgent.
Despite the name, the implementation is now a tool-calling research loop
with writing, review, and refinement stages.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from agent.tools import is_search_engine_available
from core.embedding import is_embedding_configured
from core.llm_client import LLMClient, auto_build_client

from .graph import build_ps_agent_graph, build_test_graph
from .state import PSAgentState, create_initial_state

logger = logging.getLogger(__name__)

StepCallback = Callable[[str], None]


def check_ps_agent_requirements() -> tuple[bool, list[str]]:
    """检查 PS Agent 所需依赖是否已配置。

    Returns:
        (是否全部就绪, 缺失项描述列表)。若全部就绪则 missing 为空。
    """
    missing: list[str] = []
    if not is_embedding_configured():
        missing.append(
            "Embedding（需配置 EMBEDDING_API_KEY 与 config.toml [embedding]）"
        )
    if not is_search_engine_available():
        missing.append("Tavily（需配置 TAVILY_API_KEY）")
    return (len(missing) == 0, missing)


def _ensure_ps_agent_requirements() -> None:
    """PS Agent 运行前强制校验依赖；未配置则抛出 ValueError。"""
    ok, missing = check_ps_agent_requirements()
    if not ok:
        raise ValueError(
            "使用 PS Agent 前请先配置以下依赖: " + "；".join(missing)
        )


class PlanSolveAgent:
    """A strongly agentic daily research-and-report agent.

    The workflow is bounded by budgets to avoid runaway loops:
    - max_context_items: the number of items in the context
    """

    def __init__(
        self,
        client: Optional[LLMClient] = None,
        auduit_client: Optional[LLMClient] = None,
        *,
        max_context_items: int = 15,
        lazy_init: bool = False,
        debug: bool = False,
    ):
        self._client = client
        self._audit_client = auduit_client
        self._debug = debug
        self._graph = None
        self._on_step: Optional[StepCallback] = None
        self._last_state: PSAgentState | None = None

        self.max_context_items = max_context_items

        if not lazy_init and client is None:
            self._init_client()

    def _init_client(self) -> None:
        if self._client is None:
            self._client = auto_build_client("model")
        if self._audit_client is None:
            self._audit_client = auto_build_client("lightweight_model")
        if self._graph is None:
            if self._debug:
                self._graph = build_test_graph(self._client, self._audit_client)
            else:
                self._graph = build_ps_agent_graph(self._client, self._audit_client)

    @property
    def client(self) -> LLMClient:
        self._init_client()
        return self._client  # type: ignore[return-value]

    @property
    def graph(self):
        self._init_client()
        return self._graph

    async def run(self, focus: str, on_step: Optional[StepCallback] = None) -> str:
        """Run the agent and return the final report markdown."""
        if not focus or not focus.strip():
            raise ValueError("focus 不能为空")
        _ensure_ps_agent_requirements()

        self._on_step = on_step
        self._log_step(f"🚀 启动 Agentic Research Agent: {focus}")

        final_state = await self._invoke(focus.strip())
        self._last_state = final_state
        return self._process_result(final_state)

    async def run_with_state(
        self, focus: str, on_step: Optional[StepCallback] = None
    ) -> tuple[str, PSAgentState]:
        """Run the agent and return both the report and final state."""
        if not focus or not focus.strip():
            raise ValueError("focus 不能为空")
        _ensure_ps_agent_requirements()

        self._on_step = on_step
        self._log_step(f"🚀 启动 Agentic Research Agent: {focus}")
        final_state = await self._invoke(focus.strip())
        self._last_state = final_state
        report = self._process_result(final_state)
        return report, final_state

    async def _invoke(self, focus: str) -> PSAgentState:
        initial_state = create_initial_state(
            focus,
            on_step=self._on_step,
            max_context_items=self.max_context_items,
        )
        run_id = initial_state.get("run_id", "-")
        logger.info("[ps_agent] run_id=%s invoke start focus=%s", run_id, focus[:80] if focus else "")

        try:
            final_state = await self.graph.ainvoke(initial_state)
            logger.info(
                "[ps_agent] run_id=%s invoke done status=%s iterations=%d tool_calls=%d curations=%d research_items=%d",
                run_id,
                final_state.get("status", ""),
                final_state.get("iteration", 0),
                final_state.get("tool_call_count", 0),
                final_state.get("curation_count", 0),
                len(final_state.get("research_items", [])),
            )
            return final_state
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("[ps_agent] run_id=%s invoke failed error=%s", run_id, exc)
            self._log_step(f"❌ Agent 执行失败: {exc}")
            raise RuntimeError(f"Agent 执行失败: {exc}") from exc

    def _process_result(self, state: PSAgentState) -> str:
        status = state.get("status", "")
        report = state.get("final_report") or state.get("draft_report") or ""

        self._log_step(f"🧾 run_id={state.get('run_id', '-')}")
        self._log_step(
            "📊 运行统计: "
            f"iterations={state.get('iteration', 0)} "
            f"tool_calls={state.get('tool_call_count', 0)} "
            f"curations={state.get('curation_count', 0)} "
            f"research_items={len(state.get('research_items', []))} "
            f"discarded={len(state.get('discarded_items', []))}"
        )

        # Log the last few assistant messages for traceability.
        for msg in _tail_assistant_messages(state, limit=6):
            self._log_step(f"🧠 {msg}")

        if status == "completed" and report:
            self._log_step("✅ 报告生成完成")
            return report

        if report:
            self._log_step("⚠️ 未完全完成，但返回当前最优报告")
            return report

        error = state.get("last_error") or "Agent 未生成报告"
        self._log_step(f"❌ {error}")
        raise RuntimeError(error)

    def _log_step(self, message: str) -> None:
        logger.info(message)
        if self._on_step:
            self._on_step(message)


def _tail_assistant_messages(state: PSAgentState, *, limit: int = 6) -> list[str]:
    assistant_msgs: list[str] = []
    for message in reversed(state.get("messages", [])):
        if message.role != "assistant":
            continue
        content = (message.content or "").strip()
        if not content:
            continue
        assistant_msgs.append(content[:200])
        if len(assistant_msgs) >= limit:
            break
    assistant_msgs.reverse()
    return assistant_msgs


async def run_ps_agent(
    focus: str,
    on_step: Optional[StepCallback] = None,
    *,
    max_context_items: int = 15,
) -> str:
    """Convenience entrypoint mirroring the class-based API."""
    agent = PlanSolveAgent(
        max_context_items=max_context_items,
    )
    return await agent.run(focus, on_step=on_step)


__all__ = [
    "PSAgentState",
    "PlanSolveAgent",
    "check_ps_agent_requirements",
    "create_initial_state",
    "run_ps_agent",
]
