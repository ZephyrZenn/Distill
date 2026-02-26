"""Research planner node: generates search queries based on focus, dimensions, and feedback."""

from __future__ import annotations

import json
import logging

from distill_lib.core.llm_client import LLMClient
from distill_lib.core.models.llm import CompletionResponse, Message

from agent.ps_agent.prompts import (
    RESEARCH_PLANNER_PROMPT,
    RESEARCH_PLANNER_PATCH_PROMPT,
)
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.tools import get_researcher_tools

logger = logging.getLogger(__name__)


class ResearchPlannerNode:
    """Research planner: generates search queries based on focus, dimensions, and feedback.

    Responsibilities:
    1. Focus: User's research topic
    2. Dimensions: Research intent dimensions from bootstrap
    3. Feedback: Audit feedback from curation with search improvement suggestions

    The researcher does NOT check existing articles - it only generates
    search queries based on the above three inputs.
    """

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        iteration = state.get("iteration", 0)

        # Check iteration limits
        # TODO: 检查状态流转

        # Build prompt based on focus, dimensions, and feedback
        user_prompt, is_patch = self._build_user_prompt(state)
        system_prompt = (
            RESEARCH_PLANNER_PATCH_PROMPT if is_patch else RESEARCH_PLANNER_PROMPT
        )

        messages = [
            Message.system(system_prompt).set_priority(0),
            Message.user(user_prompt).set_priority(0),
        ]

        # Get tool schemas (only search_feeds and search_web)
        tools = get_researcher_tools(current_date=state["current_date"])

        # Call LLM with Tools
        try:
            mode_str = "（改进模式）" if is_patch else "（初始模式）"
            log_step(
                state,
                f"🤔 planner: 正在生成搜索查询 {mode_str} (iter={iteration+1})...",
            )

            response = await self.client.completion_with_tools(
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )

            assert isinstance(
                response, CompletionResponse
            ), f"Expected CompletionResponse, got {type(response)}"

            # Check if LLM wants to finish research (no tool calls)
            tool_calls = response.tool_calls or []
            if not tool_calls:
                logger.info("[planner] No tool calls generated.")
                return {
                    **log_step(state, "✅ planner: 未生成搜索查询，进入评审"),
                    "messages": [
                        Message.assistant(response.content or "搜索计划完成。")
                    ],
                    "status": "research",
                }

            # Return Assistant Message with ToolCalls
            rationale = response.content or "Search queries generated"
            assistant_msg = Message.assistant(content=rationale, tool_calls=tool_calls)

            log_msg = f"🛠️ planner: 生成 {len(tool_calls)} 个搜索查询"

            return {
                **log_step(state, log_msg),
                "messages": [assistant_msg],
                "iteration": iteration + 1,
                "status": "research",
                "patch_diagnosis": None,
                "audit_diagnosis": None,
            }

        except Exception as exc:
            logger.exception("[planner] failed")
            return {
                **log_step(state, f"❌ planner: 规划失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
            }

    def _build_user_prompt(self, state: PSAgentState) -> tuple[str, bool]:
        """Build user prompt from focus, dimensions, and diagnosis.

        Args:
            state: Current agent state

        Returns:
            User prompt string with JSON sections
        """

        focus = state["focus"]
        focus_dimensions = state.get("focus_dimensions", [])
        patch_diagnosis = state.get("patch_diagnosis")
        audit_analysis = state.get("audit_analysis")

        sections = []

        # 1. Research Focus
        sections.append(f"## 研究主题\n{focus}\n")
        is_patch = False
        # 2. Research Dimensions (as JSON)
        if focus_dimensions:
            # Group by priority
            dimensions_by_priority = {"critical": [], "high": [], "others": []}
            for dim in focus_dimensions:
                dim_dict = {
                    "name": dim.name,
                    "intent": dim.intent,
                    "keywords": dim.keywords,
                    "priority": dim.priority,
                }
                if dim.priority == "critical":
                    dimensions_by_priority["critical"].append(dim_dict)
                elif dim.priority == "high":
                    dimensions_by_priority["high"].append(dim_dict)
                else:
                    dimensions_by_priority["others"].append(dim_dict)

            sections.append("## 研究维度\n")
            sections.append(
                json.dumps(dimensions_by_priority, ensure_ascii=False, indent=2)
            )
            sections.append("\n")

        # 3. Diagnostic Feedback (only one of patch_diagnosis or audit_feedback will be present)
        if patch_diagnosis:
            sections.append("## 诊断报告（来自全局评审）\n")
            diagnosis_json = {
                "action_reason": patch_diagnosis.get("action_reason", ""),
                "missing_entities": patch_diagnosis.get("missing_entities", []),
                "coverage_gaps": patch_diagnosis.get("coverage_gaps", []),
                "coverage_score": patch_diagnosis.get("coverage_score", 0),
                "suggested_queries": patch_diagnosis.get("suggested_queries", []),
            }
            sections.append(json.dumps(diagnosis_json, ensure_ascii=False, indent=2))
            sections.append("\n")
            is_patch = True

        elif audit_analysis:
            sections.append("## 审计反馈（来自素材评审）\n")
            analysis_json = {
                "coverage_gaps": audit_analysis.get("coverage_gaps", []),
                "suggested_queries": audit_analysis.get("suggested_queries", []),
                "search_pivot": audit_analysis.get("search_pivot", ""),
                "reason": audit_analysis.get("reason", ""),
            }
            sections.append(json.dumps(analysis_json, ensure_ascii=False, indent=2))
            sections.append("\n")
            is_patch = True

        return "\n".join(sections), is_patch
