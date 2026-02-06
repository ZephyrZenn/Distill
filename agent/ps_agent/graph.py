"""LangGraph workflow for a highly agentic daily research agent."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from agent.ps_agent.nodes.planner import set_planner_client, bootstrap_node, research_planner_node, structure_node
from agent.ps_agent.nodes.solver import set_solver_client, tool_node, writer_node, refiner_node
from agent.ps_agent.nodes.evaluator import set_evaluator_client, material_curation_node, plan_reviewer_node, summary_reviewer_node
from core.llm_client import LLMClient
from core.models.llm import Message


from .state import PSAgentState, log_step

logger = logging.getLogger(__name__)


def curation_router(state: PSAgentState) -> Literal["research", "plan_review"]:
    """Route after curation decides.

    Routing logic:
    1. If ready_for_review=True → plan_review (global review)
    2. Otherwise → research (continue searching)
    """
    run_id = state.get("run_id", "-")
    ready_for_review = state.get("ready_for_review", False)

    if ready_for_review:
        logger.info("[route] run_id=%s curation_router=plan_review reason=ready_for_review", run_id)
        return "plan_review"

    logger.info("[route] run_id=%s curation_router=research reason=continue_search", run_id)
    return "research"


def plan_review_router(state: PSAgentState) -> Literal["research", "bootstrap", "structure"]:
    """Route after plan_reviewer performs global review.

    Routing logic:
    1. If ready_for_write=True → structure (proceed to writing)
    2. If execution_mode=REPLAN_MODE → bootstrap (restart with new dimensions)
    3. Otherwise → research (continue searching)
    """
    run_id = state.get("run_id", "-")

    # Check iteration limits
    if state["iteration"] >= state["max_iterations"]:
        logger.warning(
            "[route] run_id=%s plan_review_router=structure reason=max_iterations",
            run_id,
        )
        return "structure"

    # Check if plan_reviewer approved for writing
    if state.get("ready_for_write", False):
        logger.info("[route] run_id=%s plan_review_router=structure reason=ready_for_write", run_id)
        return "structure"

    # Check for replan mode
    mode = state.get("execution_mode", "NORMAL")
    if mode == "REPLAN_MODE":
        logger.info("[route] run_id=%s plan_review_router=bootstrap reason=replan_mode", run_id)
        return "bootstrap"

    # Default: continue research
    logger.info("[route] run_id=%s plan_review_router=research reason=continue", run_id)
    return "research"


def summary_review_router(state: PSAgentState) -> Literal["completed", "refining"]:
    """Route after reviewing a draft. Can only go to refining or completed."""
    status = state.get("status", "")
    if status == "completed":
        return "completed"
    else:
        return "refining"


def finalize_node(state: PSAgentState) -> dict:
    """Finalize the workflow into a stable completed/failed state."""
    status = state.get("status", "")

    
    if status == "completed":
        message = "审稿通过，生成最终报告。"
    else:
        message = "未完全通过审稿，但返回当前最优草稿作为最终结果。"
    print(state.get("final_report"))
    return {
        **log_step(state, f"🏁 finalize: completed status={status or 'N/A'}"),
        "status": "completed",
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
