"""LangGraph workflow for a highly agentic daily research agent."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from agent.ps_agent.nodes.planner import set_planner_client, bootstrap_node, research_planner_node, structure_node
from agent.ps_agent.nodes.solver import set_solver_client, tool_node, writer_node, refiner_node
from agent.ps_agent.nodes.evaluator import set_evaluator_client, material_curation_node, plan_reviewer_node, summary_reviewer_node
from distill_lib.core.llm_client import LLMClient
from distill_lib.core.models.llm import Message


from .state import PSAgentState, log_step

logger = logging.getLogger(__name__)


def curation_router(state: PSAgentState) -> Literal["research", "plan_review"]:
    """Route after curation decides.

    Layer 2 Circuit Breaker Logic:
    1. If ready_for_review=True → plan_review (normal exit)
    2. If iteration >= max_iterations → plan_review (force exit)
    3. If tool_call_count >= max_tool_calls → plan_review (force exit)
    4. If curation_count >= max_curations → plan_review (force exit)
    5. Otherwise → research (continue searching)
    """
    run_id = state.get("run_id", "-")
    ready_for_review = state.get("ready_for_review", False)

    # Layer 2: Get limits
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 10)
    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 50)
    curation_count = state.get("curation_count", 0)
    max_curations = state.get("max_curations", 8)

    # Priority 1: Ready for review (normal exit)
    if ready_for_review:
        logger.info("[route] run_id=%s curation_router=plan_review reason=ready_for_review", run_id)
        return "plan_review"

    # Priority 2: Circuit breaker - force exit to next phase
    if iteration >= max_iterations:
        logger.warning(
            "[route] run_id=%s curation_router=plan_review reason=max_iterations (%d>=%d)",
            run_id, iteration, max_iterations
        )
        return "plan_review"

    if tool_call_count >= max_tool_calls:
        logger.warning(
            "[route] run_id=%s curation_router=plan_review reason=max_tool_calls (%d>=%d)",
            run_id, tool_call_count, max_tool_calls
        )
        return "plan_review"

    if curation_count >= max_curations:
        logger.warning(
            "[route] run_id=%s curation_router=plan_review reason=max_curations (%d>=%d)",
            run_id, curation_count, max_curations
        )
        return "plan_review"

    # Default: continue research
    logger.info("[route] run_id=%s curation_router=research reason=continue_search", run_id)
    return "research"


def plan_review_router(state: PSAgentState) -> Literal["research", "bootstrap", "structure"]:
    """Route after plan_reviewer performs global review.

    Layer 2 Circuit Breaker Logic:
    1. If ready_for_write=True → structure (proceed to writing)
    2. If plan_review_count >= max_plan_reviews → structure (force exit)
    3. If iteration >= max_iterations or tool_call_count >= max_tool_calls → structure (force exit)
    4. If execution_mode=REPLAN_MODE → bootstrap (only if under limits)
    5. Otherwise → research (continue searching)
    """
    run_id = state.get("run_id", "-")

    # Layer 2: Get limits
    plan_review_count = state.get("plan_review_count", 0)
    max_plan_reviews = state.get("max_plan_reviews", 3)
    iteration = state.get("iteration", 0)
    max_iterations = state.get("max_iterations", 10)
    tool_call_count = state.get("tool_call_count", 0)
    max_tool_calls = state.get("max_tool_calls", 50)

    # Priority 1: Ready for write (normal exit)
    if state.get("ready_for_write", False):
        logger.info("[route] run_id=%s plan_review_router=structure reason=ready_for_write", run_id)
        return "structure"

    # Priority 2: Circuit breaker - force exit to writing (graceful degradation)
    if plan_review_count >= max_plan_reviews:
        logger.warning(
            "[route] run_id=%s plan_review_router=structure reason=max_plan_reviews (%d>=%d)",
            run_id, plan_review_count, max_plan_reviews
        )
        return "structure"

    if iteration >= max_iterations or tool_call_count >= max_tool_calls:
        logger.warning(
            "[route] run_id=%s plan_review_router=structure reason=limits_exceeded iter=%d/%d tools=%d/%d",
            run_id, iteration, max_iterations, tool_call_count, max_tool_calls
        )
        return "structure"

    # Priority 3: Check for replan mode (only if under limits)
    mode = state.get("execution_mode", "NORMAL")
    if mode == "REPLAN_MODE":
        logger.info("[route] run_id=%s plan_review_router=bootstrap reason=replan_mode", run_id)
        return "bootstrap"

    # Default: continue research
    logger.info("[route] run_id=%s plan_review_router=research reason=continue", run_id)
    return "research"


def summary_review_router(state: PSAgentState) -> Literal["completed", "refining"]:
    """Route after reviewing a draft.

    Layer 2 Circuit Breaker Logic:
    1. If status=completed → completed (normal exit)
    2. If refine_count >= max_refines → completed (force exit with best effort)
    3. Otherwise → refining (continue refining)
    """
    run_id = state.get("run_id", "-")
    status = state.get("status", "")

    # Priority 1: Normal completion
    if status == "completed":
        return "completed"

    # Layer 2: Circuit breaker - check refine limit
    refine_count = state.get("refine_count", 0)
    max_refines = state.get("max_refines", 3)

    if refine_count >= max_refines:
        logger.warning(
            "[route] run_id=%s summary_review_router=completed reason=max_refines (%d>=%d)",
            run_id, refine_count, max_refines
        )
        return "completed"

    # Default: continue refining
    return "refining"


def finalize_node(state: PSAgentState) -> dict:
    """Finalize the workflow into a stable completed/failed state."""
    status = state.get("status", "")
    final_report = state.get("final_report")

    if status == "completed":
        message = "审稿通过，生成最终报告。"
    else:
        message = "未完全通过审稿，但返回当前最优草稿作为最终结果。"
        # 因 max_refines 等强制结束时，若尚未有 final_report 则从 sections 拼出当前最优草稿
        if not final_report:
            sections = state.get("sections", [])
            if sections:
                final_report = "\n".join(
                    section.get("content", "") or "" for section in sections
                ).strip()
                if final_report:
                    logger.info(
                        "[finalize] assembled best-effort report from %d sections (%d chars)",
                        len(sections),
                        len(final_report),
                    )

    return {
        **log_step(state, f"🏁 finalize: completed status={status or 'N/A'}"),
        "status": "completed",
        "final_report": final_report,
        "messages": [Message.assistant(message)],
    }


def build_ps_agent_graph(client: LLMClient, audit_client: LLMClient):
    """Build and compile the agentic LangGraph workflow."""
    # Register the shared client across nodes.
    set_planner_client(client)
    set_solver_client(client)
    set_evaluator_client(client, audit_client)

    graph = StateGraph(PSAgentState)

    # Nodes
    graph.add_node("bootstrap", bootstrap_node)

    # Research Phase
    graph.add_node("research", research_planner_node)
    graph.add_node("tooling", tool_node)
    graph.add_node("curation", material_curation_node)
    graph.add_node("plan_review", plan_reviewer_node)

    # Structure Phase
    graph.add_node("structure", structure_node)


    # Writing Phase
    graph.add_node("writing", writer_node)
    graph.add_node("reviewing", summary_reviewer_node)
    graph.add_node("refining", refiner_node)
    graph.add_node("finalize", finalize_node)

    # Entry
    graph.set_entry_point("bootstrap")

    # Edges
    graph.add_edge("bootstrap", "research")
    graph.add_edge("research", "tooling")
    graph.add_edge("tooling", "curation")
   
    graph.add_conditional_edges(
        "curation",
        curation_router,
        {
            "research": "research",      # Not ready → continue research
            "plan_review": "plan_review", # Ready for review → global review
        }
    )

    # Outer Review: plan_review → (research | bootstrap | structure)
    graph.add_conditional_edges(
        "plan_review",
        plan_review_router,
        {
            "research": "research",      # PATCH_MODE: continue inner loop
            "bootstrap": "bootstrap",    # REPLAN_MODE: restart
            "structure": "structure"     # ready_for_write: proceed to writing
        }
    )

    # Structure Phase
    graph.add_edge("structure", "writing")


    # Writing Phase
    graph.add_edge("writing", "reviewing")
    graph.add_conditional_edges(
        "reviewing",
        summary_review_router,
        {
            "completed": "finalize",
            "refining": "refining",
        },
    )
    graph.add_edge("refining", "reviewing")

    # Exit
    graph.add_edge("finalize", END)

    logger.info(f"[graph] Agentic daily research graph constructed (Inner Loop: research→tooling→curation→research)")
    return graph.compile()


def build_simple_graph(client: LLMClient, audit_client: LLMClient):
    """Debug-only flow: bootstrap -> research -> writing -> finalize."""
    return build_ps_agent_graph(client, audit_client)

def build_test_graph(client: LLMClient, audit_client: LLMClient):
    
    return build_ps_agent_graph(client, audit_client)

__all__ = [
    "build_ps_agent_graph",
    "build_simple_graph",
    "build_test_graph",
]
