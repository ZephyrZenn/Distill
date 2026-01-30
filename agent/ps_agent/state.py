"""State for the agentic daily-research LangGraph workflow."""

from __future__ import annotations

from datetime import datetime
from operator import add
from typing import Annotated, Callable, Literal, TypedDict
from uuid import uuid4

from typing_extensions import NotRequired

from core.models.llm import Message

StepCallback = Callable[[str], None]

from .models import FocusBucket, Feedback



class ResearchItem(TypedDict, total=False):
    """A normalized research record used for ranking and citations."""

    id: str
    title: str
    url: str
    source: str  # feed | web | memory
    published_at: str
    summary: str
    content: str
    score: float
    tags: list[str]


class Citation(TypedDict, total=False):
    """A lightweight citation entry to make reports traceable."""

    title: str
    url: str
    source: str
    published_at: str


class DiscardedItem(TypedDict, total=False):
    """An item that was dropped during curation, with a reason."""

    id: str
    title: str
    url: str
    reason: str
    score: float


class PSAgentState(TypedDict):
    """Full state for the new tool-calling research workflow."""

    # Correlation id for a single run (useful when multiple agents run concurrently).
    run_id: str

    # UI/CLI progress stream.
    log_history: Annotated[list[str], add]
    on_step: NotRequired[StepCallback]

    # User intent
    focus: str
    current_date: str
    focus_keywords: list[str]
    # Structural focus buckets for gap analysis
    focus_buckets: list[FocusBucket]


    # Conversation / tool-calling loop
    messages: Annotated[list[Message], add]
    tool_call_count: int
    max_tool_calls: int
    iteration: int
    max_iterations: int

    # Lightweight tool-call memory (to help the model avoid repeating searches)
    recent_web_queries: list[str]
    # Explicit control flag to switch to writing without relying on string sentinels.
    ready_to_write: bool
    # Optional structured conclusion captured from the model when it decides to stop researching.
    research_brief: dict | None
    
    # Feedback from the evaluator to guide the next planner step
    evaluator_feedback: Feedback | None

    # Research memory
    research_items: list[ResearchItem]
    citations: list[Citation]
    discarded_items: list[DiscardedItem]
    curation_count: int
    max_context_items: int

    # Structuring & Planning
    plan: dict | None  # AgentPlanResult
    plan_critique: dict | None
    replan_count: int
    max_replans: int
    generated_sections: list[str]

    # Writing pipeline
    draft_report: str | None
    review_result: dict | None
    final_report: str | None
    refine_count: int
    max_refine: int

    # Status / diagnostics
    status: Literal[
        "bootstrapping",
        "researching",
        "curating",
        "tooling",
        "writing",
        "reviewing",
        "refining",
        "completed",
        "failed",
    ]
    last_error: str | None


def create_initial_state(
    focus: str,
    *,
    on_step: StepCallback | None = None,
    max_iterations: int = 12,
    max_tool_calls: int = 24,
    max_refine: int = 2,
    max_context_items: int = 40,
) -> PSAgentState:
    """Create a bounded initial state for the daily research agent."""
    today = datetime.now().strftime("%Y-%m-%d")

    state = PSAgentState(
        run_id=uuid4().hex[:10],
        log_history=[],
        focus=focus,
        current_date=today,
        focus_keywords=[],
        focus_buckets=[],
        messages=[],
        tool_call_count=0,
        max_tool_calls=max_tool_calls,
        iteration=0,
        max_iterations=max_iterations,
        recent_web_queries=[],
        ready_to_write=False,
        research_brief=None,
        evaluator_feedback=None,
        research_items=[],
        citations=[],
        discarded_items=[],
        curation_count=0,
        max_context_items=max_context_items,
        draft_report=None,
        review_result=None,
        final_report=None,
        refine_count=0,
        max_refine=max_refine,
        status="bootstrapping",
        last_error=None,
        plan=None,
        plan_critique=None,
        replan_count=0,
        max_replans=3,
        generated_sections=[],
    )

    if on_step:
        state["on_step"] = on_step

    return state


def log_step(state: PSAgentState, message: str) -> dict:
    """Record a human-readable execution trace entry (and stream it if configured)."""
    callback = state.get("on_step")
    if callback:
        try:
            callback(message)
        except Exception:
            # Never fail the workflow because UI logging failed.
            pass
    return {"log_history": [message]}


__all__ = [
    "Citation",
    "DiscardedItem",
    "PSAgentState",
    "ResearchItem",
    "create_initial_state",
    "log_step",
]
