"""LLM result parsing and validation for audit."""

from __future__ import annotations

import logging
from typing import Literal

from agent.ps_agent.models import FullAuditResult, SnippetAuditResult, ResearchItem

logger = logging.getLogger(__name__)

def _process_snippet_item(
    original_item: ResearchItem,
    result_item: SnippetAuditResult,
) -> ResearchItem:
    """Process a single item in snippet stage.

    Snippet stage evaluates:
    - topic_match: How well the content matches the research topic
    - information_value: Initial quality assessment
    - matched_dimensions: Which research dimensions are covered
    - should_fetch_full: Whether to fetch full content

    Args:
        original_item: Original research item
        result_item: LLM audit result for this item

    Returns:
        Updated research item
    """
    reasoning = result_item.get("reasoning", {})
    explanation = result_item.get("explanation", "")

    # Extract scores
    relevance = result_item.get("relevance_score")

    # Build reason string
    reason_parts = [explanation] if explanation else []

    dims = reasoning.get("matched_dimensions", [])
    if dims:
        reason_parts.append(f"Dimensions: {', '.join(dims)}")

    audit_reason = " | ".join(reason_parts) if reason_parts else "No explanation"

    # Update item - preserve type by spreading original
    updated_item: ResearchItem = {
        **original_item,
        "relevance": relevance,
        "audit_stage": "snippet",
        "audit_reason": audit_reason[:500],
        "should_fetch_full": bool(result_item.get("should_fetch_full", False)),
    }

    return updated_item


def _process_full_item(
    original_item: ResearchItem,
    result_item: FullAuditResult,
) -> ResearchItem:
    """Process a single item in full stage.

    Full stage evaluates using the new FullAuditResult structure:
    - scores.refined_relevance: Refined relevance score (0.0-1.0)
    - scores.quality_score: Quality assessment score (0.0-1.0)
    - scores.novelty_score: Novelty/unique value score (0.0-1.0)
    - audit_report.key_findings: Key findings from the content
    - audit_report.reason: Explanation of the audit decision
    - audit_report.defects: Identified defects or issues

    Args:
        original_item: Original research item
        result_item: LLM audit result for this item

    Returns:
        Updated research item
    """
    scores = result_item.get("scores", {})
    audit_report = result_item.get("audit_report", {})

    # Extract scores from FullAuditScores
    llm_relevance = scores.get("refined_relevance", 0.0)
    llm_quality = scores.get("quality_score", 0.0)
    llm_novelty = scores.get("novelty_score", 0.0)

    # Build reason string from audit_report
    reason_parts = []

    reason = audit_report.get("reason", "")
    if reason:
        reason_parts.append(reason)

    key_findings = audit_report.get("key_findings", [])
    if key_findings:
        reason_parts.append(f"Findings: {'; '.join(key_findings[:3])}")

    defects = audit_report.get("defects", "")
    if defects:
        reason_parts.append(f"Defects: {defects}")

    audit_reason = " | ".join(reason_parts) if reason_parts else "No explanation"

    # Update item - preserve type by spreading original
    updated_item: ResearchItem = {
        **original_item,
        "relevance": round(llm_relevance, 4),
        "quality": round(llm_quality, 4),
        "novelty": round(llm_novelty, 4),
        "audit_stage": "full",
        "audit_reason": audit_reason[:500],
    }

    return updated_item


def parse_audit_result(
    items: list[ResearchItem],
    results: list[SnippetAuditResult] | list[FullAuditResult],
    stage: Literal["snippet", "full"] = "snippet",
) -> tuple[list[ResearchItem], list[ResearchItem]]:
    """Parse LLM audit result and separate kept/discarded items.

    Args:
        items: Original research items
        llm_result: Parsed JSON from LLM (reasoning-driven format)
        stage: "snippet" or "full"

    Returns:
        Tuple of (kept_items, discarded_items)
    """

    if not results:
        logger.warning(
            f"[result_parser] No results in LLM response, keeping all {len(items)} items"
        )
        return items, []

    # Create lookup dict (all items should have id at this point)
    item_lookup: dict[str, ResearchItem] = {
        item["id"]: item for item in items if "id" in item
    }

    kept = []
    discarded = []

    # Choose processor based on stage
    processor = _process_snippet_item if stage == "snippet" else _process_full_item

    for result_item in results:
        item_id = result_item.get("id")

        if item_id not in item_lookup:
            logger.warning(f"[result_parser] Unknown item_id: {item_id}")
            continue

        original_item = item_lookup[item_id]

        # Process item using stage-specific processor
        processed_item = processor(original_item, result_item)

        # Separate by action
        action = result_item.get("action", "keep")
        if action == "keep":
            kept.append(processed_item)
        else:
            discarded.append(processed_item)

    logger.info(
        f"[result_parser] Stage={stage}: kept={len(kept)}, discarded={len(discarded)}"
    )
    return kept, discarded


__all__ = ["parse_audit_result"]
