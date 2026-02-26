# ---------------------------------------------------------------------------
# Tool execution node
# ---------------------------------------------------------------------------

import logging
from distill_lib.core.llm_client import LLMClient
from distill_lib.core.models.llm import Message
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.tools import execute_tool_calls
from .utils import _last_tool_calls

logger = logging.getLogger(__name__)


class ToolExecutorNode:
    """Execute tool calls from the most recent assistant message."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        tool_calls = _last_tool_calls(state)
        if not tool_calls:
            return {
                **log_step(state, "ℹ️ tooling: 未检测到工具调用，继续研究/写作"),
                "status": "research",
                "messages": [
                    Message.assistant("未检测到工具调用，继续研究或进入写作。")
                ],
            }

        logger.info(
            "[tools] run_id=%s executing=%d tool_call_count=%s",
            run_id,
            len(tool_calls),
            state.get("tool_call_count", 0),
        )
        try:
            pre = log_step(
                state,
                f"🔧 tooling: 执行工具调用 {len(tool_calls)} 个: "
                + ",".join(tc.name for tc in tool_calls),
            )
            updates = await execute_tool_calls(state, tool_calls)
            updates.setdefault("status", "research")
            updates = {**pre, **updates}
            return updates
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("[tools] execution failed")
            return {
                **log_step(state, f"❌ tooling: 工具执行失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
                "messages": [Message.assistant(f"工具执行失败：{exc}")],
            }



