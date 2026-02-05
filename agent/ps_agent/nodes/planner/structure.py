import json
from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.state import PSAgentState, log_step
from agent.utils import extract_json
import logging

logger = logging.getLogger(__name__)

class StructureNode:
    """Analyze research items and generate a structured execution plan (Focal Points)."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        focus = state["focus"]
        focus_dimensions = state.get("focus_dimensions", [])

        # Format the Knowledge Base (简化版)
        kb_lines = []
        research_items = state.get("research_items", [])
        kb_lines.append(f"## 收集的材料总数: {len(research_items)} 条")
        kb_lines.append("")

        # 显示研究意图维度作为背景参考
        if focus_dimensions:
            kb_lines.append(f"## 研究意图维度 ({len(focus_dimensions)}个)")
            for d in focus_dimensions:
                kb_lines.append(f"- **{d.name}** (priority={d.priority}): {d.intent[:80]}...")
            kb_lines.append("")

        # 材料预览（按相关性排序的前 10 条）
        if research_items:
            kb_lines.append("## 高相关性材料预览")
            sorted_items = sorted(research_items, key=lambda x: x.get("composite_score", 0), reverse=True)[:10]
            for idx, item in enumerate(sorted_items[:10], 1):
                title = item.get("title", "")
                relevance = item.get("relevance", 0.0)
                kb_lines.append(f"{idx}. {title} (relevance: {relevance:.2f})")
            kb_lines.append("")

        kb_text = "\n".join(kb_lines)

        from agent.ps_agent.prompts import STRUCTURE_SYSTEM_PROMPT, STRUCTURE_USER_PROMPT
        
        # Build Messages
        messages = [
            Message.system(STRUCTURE_SYSTEM_PROMPT).set_priority(0),
            Message.user(
                STRUCTURE_USER_PROMPT.format(
                    current_date=state["current_date"],
                    focus=focus,
                    knowledge_base=kb_text
                )
            ).set_priority(0),
        ]
        
        # If this is a replan, include previous critique
        critique = state.get("plan_critique")
        if critique and state["replan_count"] > 0:
             messages.append(
                 Message.user(f"Previous Plan Critique: {json.dumps(critique, ensure_ascii=False)}")
             )

        try:
            pre = log_step(state, "📐 structuring: 正在生成写作策略...")
            response = await self.client.completion(messages)

            plan = extract_json(response)

            writing_guides = plan.get("writing_guides", [])
            daily_overview = plan.get("daily_overview", "")
            summary = f"规划完成：生成 {len(writing_guides)} 个章节指南。"

            # Log specifics
            for guide in writing_guides:
                logger.info("[structure] Chapter: %s (Priority: %s)", guide.get("chapter_name"), guide.get("priority"))

            return {
                **pre,
                **log_step(state, f"📐 structuring: {summary}"),
                "plan": plan,
                "status": "structuring",
                "messages": [Message.assistant(summary)]
            }

        except Exception as exc:
            logger.exception("[structure] failed")
            return {
                **log_step(state, f"❌ structuring: 规划失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
            }