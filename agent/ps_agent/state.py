"""State for the agentic daily-research LangGraph workflow（方案 B 简化版）."""

from __future__ import annotations

from .models import (
    AuditAnalysisResult,
    Dimension,
    PatchDiagnosis,
    ReplanDiagnosis,
    SectionUnit,
    StructurePlan,
    ResearchItem,
    DiscardedItem,
)

from datetime import datetime
from operator import add
from typing import Annotated, Callable, Literal, TypedDict
from uuid import uuid4

from typing_extensions import NotRequired

from core.models.llm import Message

StepCallback = Callable[[str], None]


class PSAgentState(TypedDict):
    """Full state for the new tool-calling research workflow（方案 B 简化版）."""

    # Correlation id for a single run (useful when multiple agents run concurrently).
    run_id: str

    # UI/CLI progress stream (on_step only; no persistent log in state).
    on_step: NotRequired[StepCallback]

    # User intent
    focus: str
    current_date: str
    # Focus dimensions for precise query generation
    focus_dimensions: NotRequired[list[Dimension]]
    # Negative keywords for filtering (extracted by bootstrap)
    negative_keywords: NotRequired[list[str]]

    # 路由
    execution_mode: Literal["NORMAL", "PATCH_MODE", "REPLAN_MODE", "READY_TO_WRITE"]

    # Conversation / tool-calling loop
    messages: Annotated[list[Message], add]
    tool_call_count: int
    iteration: int

    # Layer 1: Maximum limits (state-level hard limits)
    max_iterations: int
    max_tool_calls: int
    max_curations: int
    max_plan_reviews: int
    max_refines: int

    # Layer 2: Tracking counters (for router-level circuit breakers)
    plan_review_count: int
    refine_count: int

    # Circuit breaker tracking
    circuit_breaker_tripped: bool
    circuit_breaker_reason: str | None
    enable_hard_limits: NotRequired[bool]  # Enable Layer 1 hard limits (default: true)

    # Research memory
    research_items: list[ResearchItem]
    discarded_items: list[DiscardedItem]
    curation_count: int
    max_context_items: int

    # Audit state (P0: Two-stage LLM audit)
    audit_analysis: NotRequired[AuditAnalysisResult | None]  # Latest audit analysis
    audit_stage: NotRequired[Literal["snippet", "full"]]  # Current audit stage
    audit_batch_size: NotRequired[int]  # Configurable batch size (default: 15)
    ready_for_review: NotRequired[
        bool
    ]  # Set by curation: materials ready for plan review

    query_history: NotRequired[
        list[dict]
    ]  # [{query, timestamp, results_count, embedding}]
    # Plan review output (consumed by structure node)
    ready_for_write: NotRequired[
        bool
    ]  # Set by plan_review: materials ready for writing
    audit_memo: NotRequired[
        dict | None
    ]  # Audit memo with key findings, conflicts, gaps
    patch_diagnosis: PatchDiagnosis | None
    replan_diagnosis: ReplanDiagnosis | None

    # Structuring & Planning
    plan: StructurePlan | None  # Structure plan with writing_guides

    # Writing pipeline
    sections: list[SectionUnit]
    final_report: str | None

    # Status / diagnostics
    status: Literal[
        "bootstrapping",
        "research",
        "curating",
        "tooling",
        "structuring",
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
    max_context_items: int = 15,
    max_iterations: int = 10,
    max_tool_calls: int = 50,
    max_curations: int = 8,
    max_plan_reviews: int = 3,
    max_refines: int = 3,
) -> PSAgentState:
    """Create a bounded initial state for the daily research agent（方案 B 简化版）。"""
    today = datetime.now().strftime("%Y-%m-%d")

    state = PSAgentState(
        run_id=uuid4().hex[:10],
        focus=focus,
        current_date=today,
        execution_mode="NORMAL",
        messages=[],
        tool_call_count=0,
        iteration=0,
        # Layer 1: Maximum limits
        max_iterations=max_iterations,
        max_tool_calls=max_tool_calls,
        max_curations=max_curations,
        max_plan_reviews=max_plan_reviews,
        max_refines=max_refines,
        # Layer 2: Tracking counters (initialize to 0)
        plan_review_count=0,
        refine_count=0,
        # Circuit breaker tracking
        circuit_breaker_tripped=False,
        circuit_breaker_reason=None,
        enable_hard_limits=True,
        # Research memory
        research_items=[],
        discarded_items=[],
        curation_count=0,
        max_context_items=max_context_items,
        # Plan review output
        ready_for_review=False,
        ready_for_write=False,
        audit_memo=None,
        patch_diagnosis=None,
        replan_diagnosis=None,
        # Structuring & Planning
        plan=None,
        # Writing pipeline
        sections=[],
        final_report=None,
        # Status / diagnostics
        status="bootstrapping",
        last_error=None,
    )

    if on_step:
        state["on_step"] = on_step

    return state


def log_step(state: PSAgentState, message: str) -> dict:
    """Emit a progress message via on_step callback (if configured). No state update."""
    callback = state.get("on_step")
    if callback:
        try:
            callback(message)
        except Exception:
            # Never fail the workflow because UI logging failed.
            pass
    return {}


def check_layer1_limits(state: PSAgentState, counter_name: str, counter_value: int) -> tuple[bool, str | None]:
    """Check Layer 1 hard limits and return (should_fail, reason).

    Args:
        state: Current agent state
        counter_name: Name of the counter being checked
            (e.g., "iteration", "tool_call_count", "curation_count",
                  "plan_review_count", "refine_count")
        counter_value: Current value of the counter

    Returns:
        (should_fail, error_reason) tuple
        - should_fail: True if the limit is exceeded
        - error_reason: Human-readable reason string if should_fail=True

    Example:
        should_fail, reason = check_layer1_limits(state, "iteration", 11)
        if should_fail:
            return {"status": "failed", "last_error": reason}
    """
    enable_hard_limits = state.get("enable_hard_limits", True)
    if not enable_hard_limits:
        return False, None

    limits = {
        "iteration": ("max_iterations", state.get("max_iterations", 10)),
        "tool_call_count": ("max_tool_calls", state.get("max_tool_calls", 50)),
        "curation_count": ("max_curations", state.get("max_curations", 8)),
        "plan_review_count": ("max_plan_reviews", state.get("max_plan_reviews", 3)),
        "refine_count": ("max_refines", state.get("max_refines", 3)),
    }

    if counter_name not in limits:
        return False, None

    max_key, max_value = limits[counter_name]

    if counter_value >= max_value:
        reason = f"Layer 1 limit exceeded: {counter_name}={counter_value} >= {max_key}={max_value}"
        return True, reason

    return False, None


__all__ = [
    "PSAgentState",
    "create_initial_state",
    "log_step",
    "check_layer1_limits",
]
