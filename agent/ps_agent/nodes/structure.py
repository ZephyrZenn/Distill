"""Structuring nodes: Break down research into focal points and critique the plan."""

from __future__ import annotations

import json
import logging

from agent.ps_agent.state import PSAgentState, log_step
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
        items = state.get("research_items", [])
        
        # 1. Group items by Bucket (Using updated logic without tags)
        buckets = state.get("focus_buckets", [])
        
        # Build map: ItemID -> List[BucketName]
        item_bucket_map: dict[str, list[str]] = {}
        for b in buckets:
            bname = b["name"]
            # We assume curation populated 'matched_item_ids'
            matched_ids = b.get("matched_item_ids", [])
            for mid in matched_ids:
                if mid not in item_bucket_map:
                    item_bucket_map[mid] = []
                # Use bucket name for grouping in display
                item_bucket_map[mid].append(bname)
        
        # Prepare "Bucket Knowledge Base"
        knowledge_base = {}
        general_pool = []
        
        for item in items:
            eid = str(item.get("id"))
            
            # Find which bucket names this item belongs to
            bnames = item_bucket_map.get(eid, [])
            
            if bnames:
                for bname in bnames:
                    if bname not in knowledge_base:
                        knowledge_base[bname] = []
                    # Add to the bucket group (references same object, cheap)
                    knowledge_base[bname].append(item)
            else:
                general_pool.append(item)

                
        # Format the Knowledge Base string
        kb_lines = []
        
        # Part A: Structured Buckets
        for b in buckets:
            bname = b["name"]
            items_in_bucket = knowledge_base.get(bname, [])
            status = b.get("status", "EMPTY")
            kb_lines.append(f"## Dimension: {bname} (Status: {status})")
            if not items_in_bucket:
                kb_lines.append("(No specific items matched)")
            else:
                for idx, item in enumerate(items_in_bucket, 1):
                    # Format: [ID] Title (Source) - Summary
                    i_str = f"- [{item.get('id')}] {item.get('title')} ({item.get('source')})\n  Summary: {item.get('summary')}"
                    kb_lines.append(i_str)
            kb_lines.append("")
            
        # Part B: General Pool
        if general_pool:
            kb_lines.append("## General / Uncategorized Context")
            for item in general_pool:
                i_str = f"- [{item.get('id')}] {item.get('title')} ({item.get('source')})\n  Summary: {item.get('summary')}"
                kb_lines.append(i_str)
                
        kb_text = "\n".join(kb_lines)

        from agent.ps_agent.prompts import STRUCTURE_SYSTEM_PROMPT, STRUCTURE_USER_PROMPT
        
        # 3. Build Messages
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
            pre = log_step(state, "📐 structuring: 正在深度规划 (Structure Phase)...")
            response = await self.client.completion(messages)
            
            # Use StructurePlanResult type hint although runtime doesn't enforce
            from agent.models import StructurePlanResult
            plan: StructurePlanResult = extract_json(response)
            
            focal_points = plan.get("focal_points", [])
            summary = f"规划完成：生成 {len(focal_points)} 个深度焦点。"
            
            # Log specifics
            for fp in focal_points:
                logger.info("[structure] Point: %s (Strategy: %s)", fp.get("topic"), fp.get("strategy"))

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




# LangGraph wiring helpers ---------------------------------------------------

_structure_node: StructureNode | None = None


def set_structure_client(client: LLMClient) -> None:
    global _structure_node, _critique_node
    _structure_node = StructureNode(client)


async def structure_node(state: PSAgentState) -> dict:
    if _structure_node is None:
        raise RuntimeError("Structure client not initialized.")
    return await _structure_node(state)




__all__ = ["structure_node", "set_structure_client"]
