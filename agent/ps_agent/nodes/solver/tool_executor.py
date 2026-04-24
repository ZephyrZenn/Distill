# ---------------------------------------------------------------------------
# Tool execution node
# ---------------------------------------------------------------------------

import logging
from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.tools import execute_tool_calls
from agent.tracing import trace_event
from .utils import _last_tool_calls

logger = logging.getLogger(__name__)


class ToolExecutorNode:
    """Execute tool calls from the most recent assistant message."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        tool_calls = _last_tool_calls(state)
        logger.info(
            "[ps_agent] run_id=%s node=tooling entry tool_calls=%d",
            run_id, len(tool_calls) if tool_calls else 0,
        )
        if not tool_calls:
            log_step(state, trace_event("tooling.none"))
            return {
                "status": "research",
                "messages": [
                    Message.assistant("未检测到工具调用，继续研究或进入写作。")
                ],
            }

        logger.info(
            "[ps_agent] run_id=%s node=tooling executing tools=%s tool_call_count=%s",
            run_id, [tc.name for tc in tool_calls], state.get("tool_call_count", 0),
        )
        try:
            log_step(
                state,
                trace_event("tooling.start", count=len(tool_calls)),
            )
            updates = await execute_tool_calls(state, tool_calls)
            updates.setdefault("status", "research")
            return updates
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("[tools] execution failed")
            log_step(state, trace_event("tooling.failed", error=exc))
            return {
                "status": "failed",
                "last_error": str(exc),
                "messages": [Message.assistant(f"工具执行失败：{exc}")],
            }


