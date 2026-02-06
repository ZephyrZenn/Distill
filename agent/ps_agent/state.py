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

    # UI/CLI progress stream.
    log_history: Annotated[list[str], add]
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
    max_tool_calls: int
    iteration: int
    max_iterations: int

    # Lightweight tool-call memory (to help the model avoid repeating searches)
    recent_web_queries: list[str]

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

    # Spiral collection (P1)
    spiral_iteration: NotRequired[int]  # Current spiral iteration
    max_spirals: NotRequired[int]  # Max spiral iterations (default: 3)
    query_history: NotRequired[
        list[dict]
    ]  # [{query, timestamp, results_count, embedding}]
    dimension_coverage: NotRequired[dict[str, dict]]  # Per-dimension coverage tracking

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
    max_iterations: int = 12,
    max_tool_calls: int = 24,
    max_refine: int = 2,
    max_context_items: int = 40,
) -> PSAgentState:
    """Create a bounded initial state for the daily research agent（方案 B 简化版）。"""
    today = datetime.now().strftime("%Y-%m-%d")

    state = PSAgentState(
        run_id=uuid4().hex[:10],
        log_history=[],
        focus=focus,
        current_date=today,
        execution_mode="NORMAL",
        messages=[],
        tool_call_count=0,
        max_tool_calls=max_tool_calls,
        iteration=0,
        max_iterations=max_iterations,
        recent_web_queries=[],
        research_items=[],
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
        replan_diagnosis=None,
        patch_diagnosis=None,
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
    "PSAgentState",
    "create_initial_state",
    "log_step",
]
