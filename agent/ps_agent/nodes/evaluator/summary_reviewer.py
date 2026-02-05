from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.tools.ps_writer import ps_review_article, PSWritingMaterial
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

class SummaryReviewerNode:
    """Review the draft and decide whether to refine or continue research."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        draft = state.get("draft_report")
        if not draft:
            return {
                **log_step(state, "❌ reviewing: draft_report 为空，无法审稿"),
                "status": "failed",
                "last_error": "draft_report 为空",
                "messages": [Message.assistant("无法审稿：没有草稿内容。")],
            }

        material = _build_writing_material(state)

        try:
            pre = log_step(state, "🧪 reviewing: 开始审稿")
            review = await ps_review_article(self.client, draft, material)
            logger.info(
                "[review] run_id=%s status=%s score=%s missing_info=%d",
                run_id,
                review.get("status"),
                review.get("score"),
                len(review.get("findings") or []),
            )
            return {
                **pre,
                **log_step(
                    state,
                    f"🧪 reviewing: 完成 status={review.get('status')} score={review.get('score')}",
                ),
                "review_result": review,
                "status": "reviewing",
                "last_error": None,
                "messages": [
                    Message.assistant(
                        f"审稿完成：status={review.get('status')} score={review.get('score')}"
                    )
                ],
            }
        except Exception as exc:
            logger.exception("[review] failed")
            return {
                **log_step(state, f"❌ reviewing: 审稿失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
                "messages": [Message.assistant(f"审稿阶段失败：{exc}")],
            }

