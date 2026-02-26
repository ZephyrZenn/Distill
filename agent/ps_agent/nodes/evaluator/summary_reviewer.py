import logging
from agent.ps_agent.models import ReviewResult, SectionUnit
from agent.ps_agent.prompts.review import (
    SUMMARY_REVIEWER_PROMPT,
    SUMMARY_REVIEWER_SYSTEM_PROMPT,
)
from agent.ps_agent.state import PSAgentState, log_step
from distill_lib.core.utils import extract_json
from distill_lib.core.llm_client import LLMClient
from distill_lib.core.models.llm import Message

logger = logging.getLogger(__name__)


class SummaryReviewerNode:
    """Review the draft and decide whether to refine or continue research."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        if not state.get("sections"):
            return {
                **log_step(state, "❌ reviewing: sections 为空，无法审稿"),
                "status": "failed",
                "last_error": "sections 为空",
                "messages": [Message.assistant("无法审稿：没有章节内容。")],
            }

        sections = state.get("sections", [])
        msg_start = "🧪 reviewing: 开始审稿"
        log_step(state, msg_start)
        for section in sections:
            review = await self._review(section)
            section["review_result"] = review
        # 检查是否所有章节都通过了审核
        if all(
            section["review_result"].get("status") == "APPROVED" for section in sections
        ):
            final_report = "\n".join([section["content"] for section in sections])
            msg_done = "🧪 reviewing: 文章审核通过"
            log_step(state, msg_done)
            return {
                "log_history": [msg_start, msg_done],
                "final_report": final_report,
                "sections": sections,
                "status": "completed",
                "messages": [Message.assistant("文章审核通过")],
            }
        msg_done = "🧪 reviewing: 部分段落审核未通过，进入修订阶段"
        log_step(state, msg_done)
        return {
            "log_history": [msg_start, msg_done],
            "sections": sections,
            "status": "refining",
            "messages": [Message.assistant("部分段落审核未通过")],
        }

    async def _review(self, section: SectionUnit) -> ReviewResult:
        user_prompt = SUMMARY_REVIEWER_PROMPT.format(
            global_outline=section["context"]["global_outline"],
            chapter=section["chapter"],
            context=section["context"]["previous_summary"],
            items=section["items"],
            draft=section["content"],
        )
        messages = [
            Message.system(SUMMARY_REVIEWER_SYSTEM_PROMPT),
            Message.user(user_prompt),
        ]
        response = await self.client.completion(messages)
        result: ReviewResult = extract_json(response)
        return result
