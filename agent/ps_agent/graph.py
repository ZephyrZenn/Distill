"""LangGraph workflow for a highly agentic daily research agent."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, StateGraph

from core.llm_client import LLMClient
from core.models.llm import Message

from .nodes.curation import curation_node, set_curation_client
from .nodes.evaluator import (
    review_router,
    reviewer_node,
    refiner_node,
    set_evaluator_client,
    tool_node,
)
from .nodes.planner import planner_node, set_planner_client
from .nodes.solver import (
    set_solver_client,
    research_planner_node, 
    research_evaluator_node
)
from .nodes.structure import (
    set_structure_client,
    structure_node,
)
from .nodes.writer import set_writer_client, writer_node
from .state import PSAgentState, log_step

logger = logging.getLogger(__name__)


def research_router(state: PSAgentState) -> Literal["tooling", "evaluator"]:
    """Route after planner generates tool calls."""
    # If the planner generated tool calls, go to tooling.
    # If not (e.g., finished or empty), go to evaluator (or structure?).
    # Actually if planner says "no tools", it might mean "done".
    # ResearchPlanner leaves a message.
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        return "tooling"
    return "evaluator"


def evaluator_router(state: PSAgentState) -> Literal["structure", "research"]:
    """Route after evaluator checks sufficiency."""
    if state.get("ready_to_write"):
        return "structure"
    return "research"


def finalize_node(state: PSAgentState) -> dict:
    """Finalize the workflow into a stable completed/failed state."""
    draft = state.get("draft_report")
    review = state.get("review_result") or {}
    review_status = str(review.get("status", "")).upper()

    if draft:
        if review_status == "APPROVED":
            message = "审稿通过，生成最终报告。"
        else:
            message = "未完全通过审稿，但返回当前最优草稿作为最终结果。"
        return {
            **log_step(state, f"🏁 finalize: completed review_status={review_status or 'N/A'}"),
            "final_report": draft,
            "status": "completed",
            "last_error": None,
            "messages": [Message.assistant(message)],
        }

    return {
        **log_step(state, "🏁 finalize: failed (no draft_report)"),
        "status": "failed",
        "last_error": state.get("last_error") or "未能生成报告",
        "messages": [Message.assistant("流程结束，但没有可用报告。")],
    }


def build_ps_agent_graph(client: LLMClient):
    """Build and compile the agentic LangGraph workflow."""
    # Register the shared client across nodes.
    set_planner_client(client)
    set_solver_client(client)
    set_curation_client(client)
    set_structure_client(client)
    set_writer_client(client)
    set_evaluator_client(client)

    graph = StateGraph(PSAgentState)

    # Nodes
    graph.add_node("bootstrap", planner_node)
    
    # Research Phase
    graph.add_node("research", research_planner_node)
    graph.add_node("tooling", tool_node)
    graph.add_node("curation", curation_node)
    graph.add_node("evaluator", research_evaluator_node)

    # Structure Phase
    graph.add_node("structure", structure_node)

    
    # Writing Phase
    graph.add_node("writing", writer_node)
    graph.add_node("reviewing", reviewer_node)
    graph.add_node("refining", refiner_node)
    graph.add_node("finalize", finalize_node)

    # Entry
    graph.set_entry_point("bootstrap")

    # Edges
    graph.add_edge("bootstrap", "research")
    
    # Research Loop: Planner -> (Tooling -> Curation) or Evaluator
    graph.add_conditional_edges(
        "research",
        research_router,
        {
            "tooling": "tooling",
            "evaluator": "evaluator",
        }
    )
    graph.add_edge("tooling", "curation")
    graph.add_edge("curation", "evaluator")
    
    # Evaluator -> Structure (Ready) or Research (Loop)
    graph.add_conditional_edges(
        "evaluator",
        evaluator_router,
        {
            "structure": "structure",
            "research": "research"
        }
    )

    # Structure Phase
    graph.add_edge("structure", "writing")


    # Writing Phase
    graph.add_edge("writing", "reviewing")
    graph.add_conditional_edges(
        "reviewing",
        review_router,
        {
            "completed": "finalize",
            "refining": "refining",
            "researching": "research", # Fallback if reviewer demands more research (though rare now)
        },
    )
    graph.add_edge("refining", "reviewing")

    # Exit
    graph.add_edge("finalize", END)

    logger.info("Agentic daily research graph constructed (Batch Strategy)")
    return graph.compile()


def build_simple_graph(client: LLMClient):
    """Debug-only flow: bootstrap -> research -> writing -> finalize."""
    return build_ps_agent_graph(client)


__all__ = [
    "build_ps_agent_graph",
    "build_simple_graph",
]
