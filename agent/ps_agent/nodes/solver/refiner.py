from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.tools.ps_writer import PSWritingMaterial, ps_write_article
import logging

logger = logging.getLogger(__name__)

def _build_writing_material(state: PSAgentState) -> PSWritingMaterial:
    """从 state 构建 PSWritingMaterial（方案 B: 使用全局 items）"""
    return PSWritingMaterial(
        topic=state.get("focus", ""),
        writing_guide=state.get("writing_guide", ""),
        items=state.get("research_items", []),  # 全局材料池
        patch_items=[
            item for item in state.get("research_items", [])
            if item.get("is_patch", False)
        ],
    )

class RefinerNode:
    """Refine the draft using review feedback (no new tool calls)."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        review = state.get("review_result") or {}
        material = _build_writing_material(state)

        if state.get("refine_count", 0) >= state.get("max_refine", 0):
            logger.warning("[refine] refine budget exhausted")
            return {
                "status": "completed",
                "final_report": state.get("draft_report"),
                "messages": [
                    Message.assistant("达到修订上限，使用当前草稿作为最终结果。")
                ],
            }

        try:
            pre = log_step(
                state,
                f"🧩 refining: 根据审稿意见修订 (refine_count={state.get('refine_count', 0) + 1})",
            )
            current_draft = state.get("draft_report", "")
            refined = await ps_write_article(
                self.client, 
                material, 
                review=review,
                current_draft=current_draft
            )
            logger.info(
                "[refine] run_id=%s refine_count=%s refined_chars=%d",
                run_id,
                state.get("refine_count", 0) + 1,
                len(refined or ""),
            )
            return {
                **pre,
                **log_step(
                    state, f"🧩 refining: 修订完成 (chars={len(refined or '')})"
                ),
                "draft_report": refined,
                "refine_count": state.get("refine_count", 0) + 1,
                "status": "reviewing",
                "last_error": None,
                "messages": [
                    Message.assistant("已根据审稿意见完成一次修订，重新审稿。")
                ],
            }
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("[refine] failed")
            return {
                **log_step(state, f"❌ refining: 修订失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
                "messages": [Message.assistant(f"修订阶段失败：{exc}")],
            }