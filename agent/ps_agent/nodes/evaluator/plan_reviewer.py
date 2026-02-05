"""Plan review node: global LLM-based review and routing decision."""

from __future__ import annotations

import logging

from agent.ps_agent.models import PatchDiagnosis, ReplanDiagnosis
from core.llm_client import LLMClient
from core.models.llm import Message

from agent.ps_agent.state import PSAgentState, log_step, ResearchItem
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

        # Check if curation has marked ready for review
        ready_for_review = state.get("ready_for_review", False)

        if not ready_for_review:
            # Curation says not ready, continue research
            logger.info(
                f"[plan_reviewer] run_id={run_id} not ready for review, continue research"
            )
            return {
                **log_step(state, "🔄 plan_review: curation 未就绪，继续研究"),
                "status": "researching",
                "messages": [Message.assistant("素材尚未准备就绪，继续研究。")],
            }

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
            review_result = extract_json(response)

            status = review_result.get("status", "PATCH")
            reason = review_result.get("reason", "")
            coverage_score = review_result.get("coverage_score", 0.0)
            high_quality_ratio = review_result.get("high_quality_ratio", 0.0)
            key_findings = review_result.get("key_findings", [])
            conflicts = review_result.get("conflicts", [])
            gaps = review_result.get("gaps", [])
            strategic_patch_query = review_result.get("patch_query", "")
            curated_items = review_result.get("curated_items", [])

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
            elif status == "FAILED":
                return self._route_to_failed(state, review_result)
            else:  # PATCH -> PATCH_MODE
                return self._route_to_patch(state, review_result)

        except Exception as exc:
            logger.exception("[plan_reviewer] LLM review failed")
            # Fallback decision
            if len(research_items) >= 15 and iteration >= 8:
                return self._route_to_ready(
                    state,
                    {
                        "status": "READY",
                        "reason": "LLM评审失败，使用兜底决策：素材数量充足且搜索轮次足够",
                        "coverage_score": 0.6,
                        "key_findings": ["评审异常，请谨慎使用素材"],
                        "conflicts": [],
                        "gaps": ["LLM评审失败，可能存在未检测到的缺口"],
                        "curated_items": [
                            item.get("id")
                            for item in research_items
                            if item.get("composite_score", 0) >= 0.5
                        ],
                    },
                )
            else:
                return self._route_to_patch(
                    state,
                    {
                        "status": "STRATEGIC_PATCH",
                        "reason": "LLM评审失败，使用兜底决策：继续收集",
                        "strategic_patch_query": state.get("focus", "")[:50],
                    },
                )

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
        dimension_coverage = state.get("dimension_coverage", {})
        current_date = state["current_date"]

        sections = []

        # 1. Research Focus
        sections.append(f"## 当前日期\n{current_date}\n")
        sections.append(f"## 研究主题\n{focus}\n")

        # 2. Research Dimensions
        if focus_dimensions:
            sections.append("## 研究维度")
            for dim in focus_dimensions[:5]:
                sections.append(
                    f"- **{dim.name}** (priority={dim.priority}): {dim.intent[:80]}..."
                )
            sections.append("")

        # 3. Search Iteration & Efficiency
        sections.append(f"## 搜索轮次\n已进行 {iteration} 轮搜索\n")

        # 4. Dimension Coverage
        if dimension_coverage:
            sections.append("## 维度覆盖情况")
            for dim_name, cov_data in dimension_coverage.items():
                coverage = cov_data.get("coverage_score", 0)
                item_count = cov_data.get("item_count", 0)
                sections.append(f"- **{dim_name}**: {coverage:.2f} ({item_count} 条)")
            sections.append("")

        # 5. Global Statistics
        high_quality_count = sum(
            1 for item in research_items if item.get("composite_score", 0) >= 0.7
        )
        medium_quality_count = sum(
            1 for item in research_items if 0.5 <= item.get("composite_score", 0) < 0.7
        )
        low_quality_count = (
            len(research_items) - high_quality_count - medium_quality_count
        )

        avg_relevance = (
            sum(item.get("relevance", 0) for item in research_items)
            / len(research_items)
            if research_items
            else 0
        )
        avg_quality = (
            sum(item.get("quality", 0) for item in research_items) / len(research_items)
            if research_items
            else 0
        )
        avg_composite = (
            sum(item.get("composite_score", 0) for item in research_items)
            / len(research_items)
            if research_items
            else 0
        )

        sections.append("## 全局统计")
        sections.append(f"- 总素材数: {len(research_items)} 条")
        sections.append(
            f"- 高质量素材 (>=0.7): {high_quality_count} 条 ({high_quality_count/len(research_items)*100:.1f}%)"
        )
        sections.append(f"- 中等质量素材 (0.5-0.7): {medium_quality_count} 条")
        sections.append(f"- 低质量素材 (<0.5): {low_quality_count} 条")
        sections.append(f"- 平均相关性: {avg_relevance:.2f}")
        sections.append(f"- 平均质量: {avg_quality:.2f}")
        sections.append(f"- 平均综合分: {avg_composite:.2f}")
        sections.append("")

        # 6. High Quality Items (for key findings extraction)
        top_items = sorted(
            research_items, key=lambda x: x.get("composite_score", 0), reverse=True
        )[:15]

        sections.append("## 高分素材详情 (Top 15，用于提取核心论点)")
        for i, item in enumerate(top_items, 1):
            item_id = item.get("id", "")
            title = item.get("title", "")[:100]
            score = item.get("composite_score", 0)
            relevance = item.get("relevance", 0)
            quality = item.get("quality", 0)
            source = item.get("source", "")
            summary = item.get("summary", "")[:200]

            sections.append(
                f"{i}. **[{item_id}] {title}**\n"
                f"   - 来源: {source}\n"
                f"   - 综合分: {score:.2f} (相关性: {relevance:.2f}, 质量: {quality:.2f})\n"
                f"   - 摘要: {summary}..."
            )

        sections.append("")

        # 7. Recent Queries (for efficiency assessment)
        recent_queries = state.get("recent_web_queries", [])[-10:]
        if recent_queries:
            sections.append("## 最近搜索查询（用于评估搜索效率）")
            for i, query in enumerate(recent_queries, 1):
                sections.append(f"{i}. {query}")
            sections.append("")

        return "\n".join(sections)

    def _route_to_ready(self, state: PSAgentState, review_result: dict) -> dict:
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
        curated_items = review_result.get("curated_items", [])

        # Build audit memo
        audit_memo = {
            "coverage_score": coverage_score,
            "key_findings": key_findings,
            "conflicts": conflicts,
            "gaps": gaps,
            "curated_items": curated_items,
        }

        # Filter research items to only curated ones
        research_items = state.get("research_items", [])
        curated_item_ids = set(curated_items)
        curated_research_items = [
            item for item in research_items if item.get("id") in curated_item_ids
        ]

        message_parts = [
            f"✅ 全局评审通过\n\n",
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
            f"\n进入结构规划阶段。已筛选 {len(curated_research_items)} 条高质量素材。\n"
        )

        return {
            **log_step(state, f"✅ plan_review: {reason}，进入结构规划"),
            "status": "structuring",
            "research_items": curated_research_items,
            "audit_memo": audit_memo,
            "ready_for_write": True,
            "messages": [Message.assistant("".join(message_parts))],
        }

    def _route_to_patch(self, state: PSAgentState, review_result: dict) -> dict:
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
            message += f"**建议补丁查询**:\n"
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
            "messages": [Message.assistant(message)],
        }

    def _route_to_replan(self, state: PSAgentState, review_result: dict) -> dict:
        """Route to bootstrap for replanning with new dimensions.

        Args:
            state: Current agent state
            review_result: LLM review result

        Returns:
            State updates
        """
        reason = review_result.get("reason", "")
        new_directions = review_result.get("new_directions", {})
        failed_dimensions = review_result.get("failed_dimensions", [])
        suggested_pivots = review_result.get("suggested_pivots", [])
        coverage_score = review_result.get("coverage_score", 0.0)

        # Build replan diagnosis
        replan_diagnosis: ReplanDiagnosis = {
            "new_directions": new_directions,
            "replan_justification": reason,
            "failed_dimensions": failed_dimensions,
            "suggested_pivots": suggested_pivots,
            "coverage_score": coverage_score,
            "action_reason": reason,
        }

        message_parts = [
            f"🔄 搜索方向存在根本性问题，需要重新规划\n\n",
            f"评审意见: {reason}\n\n",
        ]

        if failed_dimensions:
            message_parts.append("**需废弃的维度**:\n")
            for dim in failed_dimensions:
                message_parts.append(f"- {dim}\n")
            message_parts.append("\n")

        if suggested_pivots:
            message_parts.append("**建议的研究转向**:\n")
            for pivot in suggested_pivots:
                message_parts.append(f"- {pivot}\n")
            message_parts.append("\n")

        message_parts.append("将重新生成研究维度并清空已有素材。\n")

        return {
            **log_step(state, f"🔄 plan_review: {reason}，触发重新规划"),
            "status": "researching",
            "execution_mode": "REPLAN_MODE",
            "ready_for_review": False,
            "ready_for_write": False,
            "replan_diagnosis": replan_diagnosis,
            "messages": [Message.assistant("".join(message_parts))],
        }

    def _route_to_failed(self, state: PSAgentState, review_result: dict) -> dict:
        """Route to failed state.

        Args:
            state: Current agent state
            review_result: LLM review result

        Returns:
            State updates
        """
        reason = review_result.get("reason", "")

        message = (
            f"❌ 任务失败\n\n"
            f"评审意见: {reason}\n\n"
            f"建议：重新定义研究关注点或调整研究范围。"
        )

        return {
            **log_step(state, f"❌ plan_review: {reason}，任务失败"),
            "status": "failed",
            "last_error": reason,
            "messages": [Message.assistant(message)],
        }
