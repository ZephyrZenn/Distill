import logging
from collections import defaultdict
from typing import TypedDict
from agent.ps_agent.models import SectionUnit, WritingContext, WritingMaterial
from agent.ps_agent.prompts.writing import (
    DEEP_WRITER_INITIAL_PROMPT,
    DEEP_WRITER_SYSTEM_PROMPT,
)
from agent.ps_agent.state import PSAgentState, log_step
from distill_lib.core.llm_client import LLMClient
from distill_lib.core.models.llm import Message


logger = logging.getLogger(__name__)

class DeepWriterNode:
    """Execute the writing plan using sliding window approach for coherence（方案 B 简化版）."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def _write_section_with_context(
        self,
        context: WritingContext,
        material: WritingMaterial,
    ) -> dict:
        """
        Write a single section with sliding window context.

        Args:
            context: Writing context
            material: Writing material

        Returns:
            {
                "content": str,  # Section content in markdown
                "summary": str   # Hook for next section
            }
        """
        content = await self._write(context, material)
        summary = await self._generate_summary(content)
        return content, summary

    async def __call__(self, state: PSAgentState) -> dict:
        plan = state.get("plan")
        if not plan:
            return {
                **log_step(state, "❌ writer: 无法写作，没有写作指南"),
                "status": "failed",
                "last_error": "No plan found",
            }

        daily_overview = plan.get("daily_overview", "")
        narrative_logic = plan.get("narrative_logic", "")
        research_items = state.get("research_items", [])
        item_map = {item.get("id"): item for item in research_items}
        chapters = plan.get("chapters", [])

        msg_start = f"✍️ writer: 开始滑动窗口式写作 {len(chapters)} 个章节..."
        log_step(state, msg_start)

        # Sliding window writing
        sections = []
        chapter_articles = defaultdict(list)
        for chapter in chapters:
            for item_id in chapter.get("referenced_doc_ids", []):
                item = item_map.get(item_id)
                if not item:
                    continue
                chapter_articles[chapter.get("chapter_id")].append(item)
        outline = f"概览:{daily_overview}\n\n叙事主线:{narrative_logic}"
        context = WritingContext(
            global_outline=outline,
            previous_summary="",
            section_number=0,
        )

        for idx, chapter in enumerate(chapters, 1):
            context["section_number"] = idx
            articles = chapter_articles[chapter.get("chapter_id")]
            material = WritingMaterial(
                chapter=chapter,
                items=articles,
            )

            content, summary = await self._write_section_with_context(context, material)
            sections.append(
                SectionUnit(
                    chapter=chapter,
                    items=articles,
                    content=content,
                    context=context.copy(),
                    review_result=None,
                )
            )
            context["previous_summary"] = summary

        msg_done = f"✍️ writer: 滑动窗口写作完成 (len={len(sections)})"
        log_step(state, msg_done)
        return {
            "log_history": [msg_start, msg_done],
            "sections": sections,
            "status": "reviewing",  # Next step
            "messages": [Message.assistant("采用滑动窗口式写作完成深度报告。")],
        }

    async def _write(self, context: WritingContext, material: WritingMaterial) -> str:
        """
        Write a single section with sliding window context.

        Args:
            material: Writing material

        Returns:
            str: Section content in markdown
        """
        user_prompt = DEEP_WRITER_INITIAL_PROMPT.format(
            global_outline=context["global_outline"],
            chapter=material["chapter"],
            items=material["items"],
        )
        messages = [
            Message.system(DEEP_WRITER_SYSTEM_PROMPT),
            Message.user(user_prompt),
        ]
        response = await self.client.completion(messages)
        return response.strip()

    async def _generate_summary(self, content: str) -> str:
        """
        Generate a summary for the given content.

        Args:
            content: Section content in markdown

        Returns:
            str: Summary
        """
        prompt = (
            f"""基于以下内容，用简短的语言总结核心论点（供下一章衔接）：{content}"""
        )
        messages = [
            Message.user(prompt),
        ]
        response = await self.client.completion(messages)
        return response.strip()
