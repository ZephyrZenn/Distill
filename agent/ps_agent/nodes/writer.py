"""Writer node: execute the plan and generate deep-dive sections."""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

from agent.models import WritingMaterial, FocalPoint
from agent.ps_agent.state import PSAgentState, ResearchItem, log_step
from agent.tools.writing_tool import write_article
from core.llm_client import LLMClient
from core.models.llm import Message

logger = logging.getLogger(__name__)


class DeepWriterNode:
    """Execute the plan (Focal Points) to generate a deep-dive report."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def _is_relevant(self, focus: str, point: FocalPoint) -> bool:
        """Lightweight check if the topic matches the focus (replaces CritiqueNode)."""
        # Fast path for broad focus
        if len(focus) < 5 or "daily" in focus.lower():
            return True
            
        topic = point.get("topic", "")
        # Use a simple heuristics or fast LLM check? 
        # User requested "Critique logic sunk to Writer", so we should probably check.
        # But to avoid infinite loops and keep speed, we can trust Structure unless egregious.
        # Let's use a very fast check if we had a small model, but here use the main client.
        
        prompt = (
            f"Focus: {focus}\nTopic: {topic}\n"
            "Is this topic strictly relevant to the focus? Answer with valid JSON {'relevant': true/false}."
        )
        try:
            # We use a lower temperature or simpler mode if possible, but here just completion
            from agent.utils import extract_json
            response = await self.client.completion([Message.user(prompt)])
            result = extract_json(response)
            is_relevant = result.get("relevant", True)
            if not is_relevant:
                 logger.warning(f"⚠️ Topic '{topic}' deemed irrelevant to focus '{focus}'. Skipping.")
            return is_relevant
        except Exception:
            return True

    async def __call__(self, state: PSAgentState) -> dict:
        plan = state.get("plan")
        if not plan or not plan.get("focal_points"):
             return {
                **log_step(state, "❌ writer: 无法写作，没有规划方案"),
                "status": "failed",
                "last_error": "No plan found",
             }
        
        focal_points = plan.get("focal_points", [])
        raw_items_map = {str(i.get("id")): i for i in state.get("research_items", [])}
        
        log_step(state, f"✍️ writer: 开始撰写 {len(focal_points)} 个专栏...")
        
        # Define the task for a single focal point
        async def process_point(point: FocalPoint) -> str:
             try:
                 # 0. Critique Check (Sunk logic)
                 if not await self._is_relevant(state["focus"], point):
                     return ""

                 # 1. Gather context
                 rss_ids = point.get("rss_ids", [])
                 web_ids = point.get("web_ids", [])
                 mem_ids = point.get("memory_ids", [])
                 
                 # Backward compatibility for old plans
                 if not rss_ids and point.get("article_ids"):
                     rss_ids = point.get("article_ids")
                 
                 rss_items = [raw_items_map[i] for i in rss_ids if i in raw_items_map]
                 web_items = [raw_items_map[i] for i in web_ids if i in raw_items_map]
                 
                 # Memories are also in research_items usually, but let's be safe
                 mem_items = []
                 for mid in mem_ids:
                     if mid in raw_items_map:
                         m = raw_items_map[mid]
                         mem_items.append({
                             "id": str(m.get("id")),
                             "topic": m.get("title", ""),
                             "reasoning": m.get("summary", ""),
                             "content": m.get("content", "")
                         })

                 # 2. Build Material
                 material = WritingMaterial(
                     topic=point["topic"],
                     style="DEEP", # Enforce Deep Dive
                     match_type=point.get("match_type", "FOCUS_MATCH"),
                     relevance_to_focus=point.get("relevance_to_focus", ""),
                     writing_guide=point.get("writing_guide", ""),
                     reasoning=point.get("reasoning", ""),
                     articles=rss_items,
                     ext_info=web_items,
                     history_memory=mem_items,
                 )
                 
                 # 3. Call Writer
                 content = await write_article(self.client, material)
                 return content
             except Exception as e:
                 logger.error(f"Failed to write section {point['topic']}: {e}")
                 return f"## {point['topic']}\n\n(撰写失败: {e})"

        # Run in parallel
        # Note: We filter empty results from skipped topics below
        sections = await asyncio.gather(*[process_point(fp) for fp in focal_points])
        sections = [s for s in sections if s.strip()]
        
        # Aggregate
        final_draft = "\n\n".join(sections)
        
        # Add Overview
        overview = plan.get("daily_overview", "")
        if overview:
            final_draft = f"# Daily Insight: {overview}\n\n{final_draft}"
            
        return {
            **log_step(state, f"✍️ writer: 写作完成 (len={len(final_draft)})"),
            "draft_report": final_draft,
            "generated_sections": sections,
            "status": "reviewing", # Next step
            "messages": [Message.assistant("深度报告撰写完成。")]
        }


# LangGraph wiring helpers ---------------------------------------------------

_writer_node: DeepWriterNode | None = None


def set_writer_client(client: LLMClient) -> None:
    global _writer_node
    _writer_node = DeepWriterNode(client)


async def writer_node(state: PSAgentState) -> dict:
    if _writer_node is None:
        raise RuntimeError("Writer client not initialized.")
    return await _writer_node(state)


__all__ = ["writer_node", "set_writer_client"]
