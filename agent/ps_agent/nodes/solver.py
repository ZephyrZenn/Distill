"""Researcher nodes: Planner and Evaluator for Batch Research Strategy."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from agent.utils import extract_json
from core.llm_client import LLMClient
from core.models.llm import Message, ToolCall

from ..prompts import (
    RESEARCH_EVALUATOR_PROMPT,
    RESEARCH_PLANNER_PROMPT,
    build_research_plan_user_prompt,
    build_research_snapshot,
)
from ..state import PSAgentState, log_step
from ..models import FocusBucket, Feedback, BucketFeedback

logger = logging.getLogger(__name__)


class ResearchPlannerNode:
    """Hypothesis-Driven Planner: Generates a batch of tool calls."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        iteration = state.get("iteration", 0)

        # 1. Check Limits
        if iteration >= state["max_iterations"]:
            return {
                **log_step(state, "🛑 planner: 达到最大轮次，强制进入评估"),
                "status": "researching",  # Will route to evaluator -> writer
                "ready_to_write": True,  # Hint to evaluator to pass? Or just let evaluator decide?
                # Actually, if we hit limit, we probably just want to write.
                # But let's let the flow handle it: Planner -> Tooling (skipped) -> Curation -> Evaluator
                # We'll return NO tool calls, so router goes to... where?
                # We need to make sure we don't loop forever.
                # Let's set a flag that we should stop.
            }

        # 2. Build Prompt
        user_prompt = build_research_plan_user_prompt(state)
        
        messages = [
            Message.system(RESEARCH_PLANNER_PROMPT).set_priority(0),
            Message.user(user_prompt).set_priority(0),
        ]

        # 3. Call LLM (JSON Mode)
        try:
            log_step(state, f"🤔 planner: 正在制定分批研究计划 (iter={iteration+1})...")
            response = await self.client.completion(messages)
            plan = extract_json(response)
            
            rationale = plan.get("rationale", "No rationale provided")
            tool_plans = plan.get("tool_plans", [])

            # 4. Convert to ToolCalls
            tool_calls = []
            for tp in tool_plans:
                name = tp.get("tool_name")
                args = tp.get("tool_args", {})
                if name:
                    tool_calls.append(ToolCall(name=name, arguments=json.dumps(args), id=str(uuid.uuid4())))

            if not tool_calls:
                # No tools planned? Maybe we are done?
                logger.info("[planner] No tools planned. Suggesting stop.")
                return {
                    "messages": [Message.assistant("No further research needed.")],
                    "status": "researching",
                }

            # 5. Return Assistant Message with ToolCalls
            # This allows ToolExecutorNode (in evaluator.py) to pick them up.
            assistant_msg = Message.assistant(
                content=f"Plan Rationale: {rationale}",
                tool_calls=tool_calls
            )
            
            log_msg = f"🛠️ planner: 生成 {len(tool_calls)} 个工具调用. 核心假设: {rationale[:50]}..."
            
            return {
                **log_step(state, log_msg),
                "messages": [assistant_msg],
                "iteration": iteration + 1,
                "status": "researching",
            }

        except Exception as exc:
            logger.exception("[planner] failed")
            return {
                **log_step(state, f"❌ planner: 规划失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
            }


class ResearchEvaluatorNode:
    """Decides if we have enough info to write the report."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        # Check hard limits first specifically here to force exit
        if state["iteration"] >= state["max_iterations"]:
             return {
                **log_step(state, "🛑 evaluator: 达到轮次上限，强制通过"),
                "ready_to_write": True,
            }

        snapshot = build_research_snapshot(state.get("research_items", []))
        
        # Build Bucket View Context (Quota Aware)
        buckets = state.get("focus_buckets", [])
        bucket_view_lines = []
        for b in buckets:
            bid = b["id"]
            name = b["name"]
            matched = b.get("matched_items", [])
            item_count = len(matched)
            quota_status = "(Quota Met)" if item_count >= 2 else f"({item_count}/2)"
            
            bucket_view_lines.append(f"[Bucket ID: {bid}] \"{name}\" {quota_status}")
            if matched:
                for idx, m_item in enumerate(matched):
                    # m_item is BucketItem TypedDict
                    title = m_item.get("title", "No Title")
                    summary = m_item.get("summary", "")[:200].replace("\n", " ")
                    sid = m_item.get("id", "")
                    
                    bucket_view_lines.append(f"  [{idx}] {title}")
                    bucket_view_lines.append(f"      ID: {sid}")
                    bucket_view_lines.append(f"      Summary: {summary}...")
                    bucket_view_lines.append("")
            else:
                bucket_view_lines.append("  - (Empty)")
            bucket_view_lines.append("") # spacer
            
        bucket_block = "\n".join(bucket_view_lines)

        prompt = f"""
Focus: {state['focus']}
Date: {state['current_date']}

Target Buckets Status (Quota Aware):
{bucket_block}

Evaluate if we are ready to write a DEEP DIVE report.
"""
        messages = [
            Message.system(RESEARCH_EVALUATOR_PROMPT).set_priority(0),
            Message.user(prompt).set_priority(0),
        ]

        try:
            log_step(state, "⚖️ evaluator: 评估信息饱和度与槽位状态...")
            response = await self.client.completion(messages)
            result = extract_json(response)
            
            status = result.get("status", "CONTINUE_RESEARCH")
            reason = result.get("reason", "")
            
            ready_to_write = (status == "READY_TO_WRITE")

            # Process Bucket Updates (P0 Feature)
            bucket_updates = result.get("bucket_updates", [])
            current_buckets = state.get("focus_buckets", [])
            # Create a dict for easier updating. Values are FocusBucket objects.
            bucket_map: dict[str, FocusBucket] = {b["id"]: b for b in current_buckets}
            
            new_blacklisted = []
            # TODO: 如何处理多次审核，都无法通过的bucket
            for update in bucket_updates:
                bid = update.get("id")
                if bid in bucket_map:
                    # Latch mechanism: Once FULL, it stays FULL.
                    if bucket_map[bid]["status"] == "FULL":
                        continue
                    else:
                        bucket_map[bid]["status"] = update.get("status", "EMPTY")
                    # NO LONGER setting missing_reason on bucket directly
                    # bucket_map[bid]["missing_reason"] = update.get("missing_reason", "")
                    
                    # Logic: Kept Index (User requested array index logic)
                    kept_indices = update.get("kept_item_idx")
                    
                    if kept_indices is not None and isinstance(kept_indices, list):
                        # Convert to set of integers
                        try:
                            kept_idx_set = {int(x) for x in kept_indices}
                        except (ValueError, TypeError):
                            logger.warning(f"[evaluator] Invalid kept_item_idx format: {kept_indices}")
                            kept_idx_set = set() # Fallback? Or strict? 
                            # If invalid, let's assume we keep nothing if format is broken, or keep all?
                            # Decision: If explicitly provided but invalid, log warning.
                            # Safe default: if parsing fails, maybe don't drop anything to be safe.
                            continue

                        current_items = bucket_map[bid].get("matched_items", [])
                        
                        final_items = []
                        dropped_ids = []
                        
                        # Iterate Items directly
                        for idx, eitem in enumerate(current_items):
                            eid = eitem.get("id", "")
                            if idx in kept_idx_set:
                                final_items.append(eitem)
                            else:
                                if eid:
                                    dropped_ids.append(eid)
                        
                        if dropped_ids:
                            logger.info(f"[evaluator] Dropping items via index strategy: {dropped_ids} (kept indices: {kept_indices})")
                            new_blacklisted.extend(dropped_ids)
                            bucket_map[bid]["matched_items"] = final_items
            
            final_buckets: list[FocusBucket] = list(bucket_map.values())
            
                    
            # Update blacklist_ids in state
            current_blacklist = set(state.get("blacklist_ids", []) or [])
            updated_blacklist = list(current_blacklist.union(new_blacklisted))

            
            # Construct feedback if not ready
            # Construct structured feedback if not ready
            feedback_payload: Feedback | None = None
            if not ready_to_write:
                bucket_fb_list: list[BucketFeedback] = []
                for update in bucket_updates:
                    # Only include relevant updates (e.g. empty/partial or with keywords)
                    status = update.get("status", "EMPTY")
                    bid = update.get("id", "")
                    
                    # We always pass back feedback if it helps planning, regardless of status change?
                    # Generally yes.
                    b_fb = BucketFeedback(
                        bucket_id=bid,
                        missing_reason=update.get("missing_reason", ""),
                        search_keywords=update.get("search_keywords", [])
                    )
                    bucket_fb_list.append(b_fb)
                
                feedback_payload = Feedback(
                    global_reason=reason,
                    bucket_feedback=bucket_fb_list
                )

            log_msg = f"⚖️ evaluator: {status}. Reason: {reason}"
            return {
                **log_step(state, log_msg),
                "ready_to_write": ready_to_write,
                "evaluator_feedback": feedback_payload,
                "focus_buckets": final_buckets,
                "blacklist_ids": updated_blacklist,
            }

        except Exception as exc:
            logger.warning(f"[evaluator] check failed: {exc}, default to CONTINUE")
            return {
                 "ready_to_write": False 
            }


# LangGraph wiring helpers ---------------------------------------------------

_planner_node: ResearchPlannerNode | None = None
_evaluator_node: ResearchEvaluatorNode | None = None


def set_solver_client(client: LLMClient) -> None:
    global _planner_node, _evaluator_node
    _planner_node = ResearchPlannerNode(client)
    _evaluator_node = ResearchEvaluatorNode(client)


async def research_planner_node(state: PSAgentState) -> dict:
    if _planner_node is None:
        raise RuntimeError("Solver client not initialized.")
    return await _planner_node(state)


async def research_evaluator_node(state: PSAgentState) -> dict:
    if _evaluator_node is None:
        raise RuntimeError("Solver client not initialized.")
    return await _evaluator_node(state)


async def solver_node(state: PSAgentState) -> dict:
    """Legacy alias if needed, mapping to planner."""
    return await research_planner_node(state)


__all__ = [
    "ResearchPlannerNode",
    "ResearchEvaluatorNode", 
    "set_solver_client", 
    "research_planner_node", 
    "research_evaluator_node",
    "solver_node"
]
