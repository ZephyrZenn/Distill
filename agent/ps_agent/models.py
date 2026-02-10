from __future__ import annotations
from typing import TypedDict, Literal

class FocusBucket(TypedDict):
    """A specific dimension of the research focus."""
    id: str              # e.g., "tech_specs"
    name: str            # "技术规格"
    description: str     # Criteria for matching items
    status: Literal["EMPTY", "PARTIAL", "FULL", "DROPPED"]
    reasoning: str       # e.g., "missing specific parameters"
    
    # Runtime fields populated during execution
    matched_items: list[BucketItem]     # Structured items

class BucketItem(TypedDict):
    """Simplified item for bucket display."""
    id: str
    title: str
    url: str
    summary: str

class BucketFeedback(TypedDict):
    """Specific feedback for a bucket."""
    bucket_id: str
    missing_reason: str
    search_keywords: list[str]

class Feedback(TypedDict):
    """Structured feedback payload from Evaluator to Planner."""
    global_reason: str
    bucket_feedback: list[BucketFeedback]

class GapAnalysis(TypedDict):
    """Result of the evaluator's gap check."""
    buckets: list[FocusBucket]
    global_status: Literal["RESEARCHING", "READY_TO_WRITE"]
    notes: str

