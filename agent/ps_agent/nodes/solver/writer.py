from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.tools.ps_writer import PSWritingMaterial, ps_write_article
from agent.utils import extract_json
import logging

logger = logging.getLogger(__name__)

class DeepWriterNode:
    """Execute the writing plan using sliding window approach for coherence（方案 B 简化版）."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def _write_section_with_context(
        self,
        guide: dict,
        context: dict,
        research_items: list
    ) -> dict:
        """
        Write a single section with sliding window context（方案 B: 不依赖 bucket）.

        Args:
            guide: Writing guide from structure node (chapter_id, chapter_name, writing_guide)
            context: {
                "global_outline": str,
                "previous_summary": str,
                "section_number": int
            }
            research_items: Global research items

        Returns:
            {
                "content": str,  # Section content in markdown
                "summary": str   # Hook for next section
            }
        """
        # Build material（方案 B: 只使用全局 research_items）
        patch_items = [i for i in research_items if i.get("is_patch")]
        material = PSWritingMaterial(
            topic=guide["chapter_name"],
            writing_guide=guide.get("writing_guide", ""),
            items=research_items,  # 全局材料池
            patch_items=patch_items,
        )

        # Call writer with context
        content = await ps_write_article(self.client, material, context=context)

        # Generate summary for next section
        summary_prompt = f"""
基于以下内容，用一句话总结核心论点（供下一章衔接）：

{content[:500]}...

输出 JSON: {{"summary": "..."}}
"""
        try:
            summary_response = await self.client.completion([Message.user(summary_prompt)])
            summary_data = extract_json(summary_response)
            summary = summary_data.get("summary", "")
        except Exception as e:
            logger.warning(f"Failed to generate summary: {e}")
            summary = f"关于{guide['chapter_name']}的分析"

        return {
            "content": content,
            "summary": summary
        }

    async def __call__(self, state: PSAgentState) -> dict:
        plan = state.get("plan")
        if not plan or not plan.get("writing_guides"):
            return {
                **log_step(state, "❌ writer: 无法写作，没有写作指南"),
                "status": "failed",
                "last_error": "No writing_guides found",
            }

        writing_guides = plan.get("writing_guides", [])
        daily_overview = plan.get("daily_overview", "")
        research_items = state.get("research_items", [])

        # Sort by priority
        writing_guides.sort(key=lambda x: x.get("priority", 99))

        log_step(state, f"✍️ writer: 开始滑动窗口式写作 {len(writing_guides)} 个章节...")

        # Sliding window writing
        sections = []
        previous_summary = ""

        for idx, guide in enumerate(writing_guides, 1):
            try:
                # Write section with context
                context = {
                    "global_outline": daily_overview,
                    "previous_summary": previous_summary,
                    "section_number": idx
                }

                result = await self._write_section_with_context(guide, context, research_items)
                sections.append(result["content"])
                previous_summary = result["summary"]

                logger.info(f"[writer] Completed section {idx}: {guide['chapter_name']}")

            except Exception as e:
                logger.error(f"Failed to write section {guide.get('chapter_name')}: {e}")
                sections.append(f"## {guide.get('chapter_name')}\n\n(撰写失败: {e})")

        # Aggregate final draft
        final_draft = "\n\n".join(sections)

        # Add Overview
        if daily_overview:
            final_draft = f"# {daily_overview}\n\n{final_draft}"

        return {
            **log_step(state, f"✍️ writer: 滑动窗口写作完成 (len={len(final_draft)})"),
            "draft_report": final_draft,
            "generated_sections": sections,
            "status": "reviewing",  # Next step
            "messages": [Message.assistant("采用滑动窗口式写作完成深度报告。")],
        }
