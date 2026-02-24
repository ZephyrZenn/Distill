"""Plan review node: global LLM-based review and routing decision."""

from __future__ import annotations

import json
import logging

from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.models import (
    PatchDiagnosis,
    PlanReviewResult,
    ReplanDiagnosis,
    ResearchItem,
)
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.prompts import PLAN_REVIEW_PROMPT
from agent.utils import extract_json

logger = logging.getLogger(__name__)


class PlanReviewerNode:
    """Plan reviewer: global LLM-based review and routing decision.

    Responsibilities:
    1. Knowledge sufficiency audit - final "stop research" decision
    2. Conflict & risk detection - identify contradictory viewpoints
    3. Efficiency & termination policy - prevent infinite low-return search
    4. Strategic routing - decide next action (READY/PATCH/FAILED)
    5. Output audit memo for structure node
    """

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")

        # Curation says ready, perform global LLM review
        research_items = state.get("research_items", [])
        iteration = state.get("iteration", 0)

        logger.info(
            f"[plan_reviewer] run_id={run_id} ready_for_review=True, "
            f"performing global LLM review on {len(research_items)} items "
            f"(iteration={iteration})"
        )

        # Build LLM prompt
        user_prompt = self._build_review_prompt(state, research_items)

        messages = [
            Message.system(PLAN_REVIEW_PROMPT),
            Message.user(user_prompt),
        ]

        try:
            # Call LLM for global review
            response = await self.client.completion(messages)
            review_result: PlanReviewResult = extract_json(response)

            status = review_result.get("status", "PATCH")
            coverage_score = review_result.get("coverage_score", 0.0)
            high_quality_ratio = review_result.get("high_quality_ratio", 0.0)

            logger.info(
                f"[plan_reviewer] run_id={run_id} LLM review: "
                f"status={status}, coverage={coverage_score:.2f}, "
                f"quality_ratio={high_quality_ratio:.2f}"
            )

            # Route based on LLM recommendation
            # Map LLM status to system status
            if status == "READY":
                return self._route_to_ready(state, review_result)
            elif status == "REPLAN":
                return self._route_to_replan(state, review_result)
            elif status == "PATCH":
                return self._route_to_patch(state, review_result)

        except Exception as exc:
            logger.exception(
                f"[plan_reviewer] run_id={run_id} LLM review failed: {exc}"
            )
            raise exc

    def _build_review_prompt(
        self, state: PSAgentState, research_items: list[ResearchItem]
    ) -> str:
        """Build user prompt for global LLM review.

        Args:
            state: Current agent state
            research_items: All research items with 5-dimensional scores

        Returns:
            User prompt string
        """
        focus = state["focus"]
        focus_dimensions = state.get("focus_dimensions", [])
        iteration = state.get("iteration", 0)
        current_date = state["current_date"]

        sections = []

        # 1. Research Focus
        sections.append(f"## 当前日期\n{current_date}\n")
        sections.append(f"## 研究主题\n{focus}\n")

        # 2. Research Dimensions
        sections.append("## 研究维度\n")
        dims = [dim.to_dict() for dim in focus_dimensions]
        sections.append(json.dumps(dims, ensure_ascii=False, indent=2))
        sections.append("\n")

        sections.append("## 素材详情\n")
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
                    "score": item.get("score", 0.0),
                    "audit_reason": item.get("audit_reason", ""),
                }
            )
        sections.append(json.dumps(items, ensure_ascii=False, indent=2))
        sections.append("\n")

        # 7. Recent Queries (for efficiency assessment)
        query_history = state.get("query_history", [])
        recent_queries = [
            item.get("query", "") for item in query_history[-10:] if item.get("query")
        ]
        if recent_queries:
            sections.append("## 最近搜索查询（用于评估搜索效率）")
            for i, query in enumerate(recent_queries, 1):
                sections.append(f"{i}. {query}")
            sections.append("")

        return "\n".join(sections)

    def _route_to_ready(
        self, state: PSAgentState, review_result: PlanReviewResult
    ) -> dict:
        """Route to structure phase with audit memo.

        Args:
            state: Current agent state
            review_result: LLM review result

        Returns:
            State updates
        """
        reason = review_result.get("reason", "")
        coverage_score = review_result.get("coverage_score", 0.0)
        key_findings = review_result.get("key_findings", [])
        conflicts = review_result.get("conflicts", [])
        gaps = review_result.get("gaps", [])
        key_items = review_result.get("key_items", [])

        # Build audit memo
        audit_memo = {
            "key_findings": key_findings,
            "conflicts": conflicts,
            "gaps": gaps,
            "key_items": key_items,
        }

        # Filter research items to only curated ones
        research_items = state.get("research_items", [])
        key_item_ids = set(key_items)
        key_research_items = [
            item for item in research_items if item.get("id") in key_item_ids
        ]

        message_parts = [
            "✅ 全局评审通过\n\n",
            f"评审意见: {reason}\n",
            f"覆盖度: {coverage_score:.2f}\n\n",
        ]

        if key_findings:
            message_parts.append("**核心发现**:\n")
            for finding in key_findings:
                message_parts.append(f"- {finding}\n")
            message_parts.append("\n")

        if conflicts:
            message_parts.append("**观点冲突** (需在写作时注意):\n")
            for conflict in conflicts:
                message_parts.append(f"- {conflict}\n")
            message_parts.append("\n")

        if gaps:
            message_parts.append("**素材缺口** (写作时需注明局限性):\n")
            for gap in gaps:
                message_parts.append(f"- {gap}\n")
            message_parts.append("\n")

        message_parts.append(
            f"\n进入结构规划阶段。已筛选 {len(key_research_items)} 条高质量素材。\n"
        )

        return {
            **log_step(state, f"✅ plan_review: {reason}，进入结构规划"),
            "status": "structuring",
            "research_items": key_research_items,
            "audit_memo": audit_memo,
            "ready_for_write": True,
            "plan_review_count": state.get("plan_review_count", 0) + 1,
            "messages": [Message.assistant("".join(message_parts))],
        }

    def _route_to_patch(
        self, state: PSAgentState, review_result: PlanReviewResult
    ) -> dict:
        """Route back to research with patch queries.

        Args:
            state: Current agent state
            review_result: LLM review result

        Returns:
            State updates
        """
        reason = review_result.get("reason", "")
        gaps = review_result.get("gaps", [])
        patch_query = review_result.get("patch_query", "")

        # Build patch diagnosis for next iteration
        # Generate suggested queries from patch_query and gaps
        suggested_queries = []
        if patch_query:
            suggested_queries.append(patch_query)
        if gaps:
            suggested_queries.extend([f"{gap} 相关新闻" for gap in gaps[:3]])

        patch_diagnosis: PatchDiagnosis = {
            "suggested_queries": suggested_queries,
            "missing_entities": gaps,
            "coverage_gaps": gaps,
            "coverage_score": review_result.get("coverage_score", 0.0),
            "action_reason": reason,
        }

        message = f"⚠️ 全局评审：{reason}\n\n"

        if suggested_queries:
            message += "**建议补丁查询**:\n"
            for q in suggested_queries[:3]:
                message += f"- {q}\n"
            message += "\n"

        message += "继续研究。"

        return {
            **log_step(state, f"⚠️ plan_review: {reason}，执行补丁搜索"),
            "status": "researching",
            "ready_for_review": False,
            "ready_for_write": False,
            "patch_diagnosis": patch_diagnosis,
            "plan_review_count": state.get("plan_review_count", 0) + 1,
            "messages": [Message.assistant(message)],
        }

    def _route_to_replan(
        self, state: PSAgentState, review_result: PlanReviewResult
    ) -> dict:
        """Route to bootstrap for replanning with new dimensions.

        Args:
            state: Current agent state
            review_result: LLM review result

        Returns:
            State updates
        """
        reason = review_result.get("reason", "")
        new_directions = review_result.get("new_directions", [])
        failed_dimensions = review_result.get("failed_dimensions", [])
        coverage_score = review_result.get("coverage_score", 0.0)

        # Build replan diagnosis
        replan_diagnosis: ReplanDiagnosis = {
            "new_directions": new_directions,
            "replan_justification": reason,
            "failed_dimensions": failed_dimensions,
            "coverage_score": coverage_score,
            "action_reason": reason,
        }

        message_parts = [
            "🔄 搜索方向存在根本性问题，需要重新规划\n\n",
            f"评审意见: {reason}\n\n",
        ]

        if failed_dimensions:
            message_parts.append("**需废弃的维度**:\n")
            for dim in failed_dimensions:
                message_parts.append(f"- {dim}\n")
            message_parts.append("\n")

        message_parts.append("将重新生成研究维度并清空已有素材。\n")

        return {
            **log_step(state, f"🔄 plan_review: {reason}，触发重新规划"),
            "status": "researching",
            "execution_mode": "REPLAN_MODE",
            "ready_for_review": False,
            "ready_for_write": False,
            "replan_diagnosis": replan_diagnosis,
            "plan_review_count": state.get("plan_review_count", 0) + 1,
            "messages": [Message.assistant("".join(message_parts))],
        }
