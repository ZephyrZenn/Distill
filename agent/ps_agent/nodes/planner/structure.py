import json
import logging
from agent.ps_agent.models import StructurePlan
from agent.ps_agent.state import PSAgentState, log_step
from agent.tracing import trace_event
from agent.ps_agent.prompts import STRUCTURE_SYSTEM_PROMPT, STRUCTURE_USER_PROMPT
from agent.utils import extract_json
from core.llm_client import LLMClient
from core.models.llm import Message

logger = logging.getLogger(__name__)


class StructureNode:
    """Analyze research items and generate a structured execution plan (Focal Points)."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        focus = state["focus"]
        focus_dimensions = state.get("focus_dimensions", [])
        audit_memo = state.get("audit_memo", {})
        # Format the Knowledge Base (简化版)
        kb_lines = []
        research_items = state.get("research_items", [])
        kb_lines.append(f"## 收集的材料总数: {len(research_items)} 条")
        kb_lines.append("")

        # 显示研究意图维度作为背景参考
        if focus_dimensions:
            kb_lines.append(f"## 研究意图维度 ({len(focus_dimensions)}个)")
            for d in focus_dimensions:
                kb_lines.append(json.dumps(d.to_dict(), ensure_ascii=False))
            kb_lines.append("")

        # 材料预览（按相关性排序的前 10 条）
        items = []
        for item in research_items:
            items.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", ""),
                    "summary": item.get("summary", ""),
                    "relevance": item.get("relevance", 0.0),
                    "quality": item.get("quality", 0.0),
                    "novelty": item.get("novelty", 0.0),
                    "content": item.get("content", ""),
                }
            )
        kb_lines.append("素材池：")
        kb_lines.append(json.dumps(items, ensure_ascii=False))
        kb_lines.append("")

        kb_text = "\n".join(kb_lines)

        # Build Messages
        messages = [
            Message.system(STRUCTURE_SYSTEM_PROMPT).set_priority(0),
            Message.user(
                STRUCTURE_USER_PROMPT.format(
                    current_date=state["current_date"],
                    focus=focus,
                    knowledge_base=kb_text,
                    audit_memo=audit_memo,
                )
            ).set_priority(0),
        ]

        run_id = state.get("run_id", "-")
        plan = state.get("plan")
        n_chapters = len(plan.get("chapters", [])) if plan else 0
        logger.info(
            "[ps_agent] run_id=%s node=structure entry plan_chapters=%d",
            run_id, n_chapters,
        )
        log_step(state, trace_event("structure.start"))  # 执行前：立即触发 callback，让 UI 先显示

        try:
            response = await self.client.completion(messages)

            plan: StructurePlan = extract_json(response)

            summary = f"规划完成：生成 {len(plan.get('chapters', []))} 个章节指南。概览：{plan.get('daily_overview', '')}"
            logger.info(
                "[structure] Finish plan. Overview: %s", plan.get("daily_overview", "")
            )

            log_step(state, trace_event("structure.completed", summary=summary))

            return {
                "plan": plan,
                "status": "structuring",
                "messages": [Message.assistant(summary)],
            }

        except Exception as exc:
            logger.exception("[structure] failed")
            log_step(state, trace_event("structure.failed", error=exc))
            return {
                "status": "failed",
                "last_error": str(exc),
            }
