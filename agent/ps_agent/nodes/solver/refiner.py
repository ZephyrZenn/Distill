from agent.ps_agent.models import SectionUnit
from agent.ps_agent.prompts.writing import DEEP_WRITER_REFINE_PROMPT, DEEP_WRITER_SYSTEM_PROMPT
from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.state import PSAgentState, log_step
from agent.tracing import trace_event
import logging

logger = logging.getLogger(__name__)

class RefinerNode:
    """Refine the draft using review feedback (no new tool calls)."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        sections = state.get("sections", [])
        failed_sections = [section for section in sections if section["review_result"].get("status") == "REJECTED"]
        logger.info(
            "[ps_agent] run_id=%s node=refiner entry sections=%d failed=%d",
            run_id, len(sections), len(failed_sections),
        )
        log_step(state, trace_event("refiner.start"))
        for section in failed_sections:
            section["content"] = await self._refine(section)
        log_step(state, trace_event("refiner.completed"))
        return {
            "sections": sections,
            "status": "writing",
            "refine_count": state.get("refine_count", 0) + 1,
            "messages": [Message.assistant("修订完成")],
        }
        
    async def _refine(self, section: SectionUnit) -> SectionUnit:
        user_prompt = DEEP_WRITER_REFINE_PROMPT.format(
            chapter_name=section["chapter"]["title"],
            global_outline=section["context"]["global_outline"],
            chapter=section["chapter"],
            review=section["review_result"],
            current_draft=section["content"],
            items=section["items"],
        )
        messages = [
            Message.system(DEEP_WRITER_SYSTEM_PROMPT),
            Message.user(user_prompt),
        ]
        response = await self.client.completion(messages)
        content = response.strip()
        return content
