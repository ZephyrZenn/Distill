from __future__ import annotations

from copy import deepcopy

from agent.models import AgentPlanResult, FocalPoint

BRIEF_ONLY = "BRIEF_ONLY"
OPTIONAL_DEEP = "OPTIONAL_DEEP"
AUTO_DEEP = "AUTO_DEEP"

_VALID_GENERATION_MODES = {BRIEF_ONLY, OPTIONAL_DEEP, AUTO_DEEP}


def normalize_plan_layers(plan: AgentPlanResult) -> AgentPlanResult:
    normalized = deepcopy(plan)
    points = normalized.get("focal_points", [])

    for point in points:
        _normalize_point_defaults(point)

    points.sort(key=lambda p: int(p.get("priority", 999)))

    if not normalized.get("today_pattern"):
        normalized["today_pattern"] = normalized.get("daily_overview", "")

    return normalized


def get_auto_deep_points(plan: AgentPlanResult) -> list[FocalPoint]:
    return [
        point
        for point in plan.get("focal_points", [])
        if _is_auto_deep(point)
    ]


def get_optional_deep_points(plan: AgentPlanResult) -> list[FocalPoint]:
    return [
        point
        for point in plan.get("focal_points", [])
        if point.get("generation_mode") == OPTIONAL_DEEP
    ]


def build_optional_analysis_section(points: list[FocalPoint]) -> str:
    if not points:
        return ""

    lines = ["## Optional Analysis", ""]
    for point in points:
        summary = str(point.get("brief_summary") or point.get("topic") or "").strip()
        reason = str(point.get("why_expand") or "").strip()
        if not summary or not reason:
            continue
        lines.append(f"- {summary} Why expand: {reason}")

    return "\n".join(lines).strip()


def assemble_layered_report(
    primary_brief: str,
    deep_sections: list[str],
    optional_points: list[FocalPoint],
) -> str:
    sections = [primary_brief.strip()]

    clean_deep_sections = [section.strip() for section in deep_sections if section.strip()]
    if clean_deep_sections:
        sections.append("## Deep Analysis\n\n" + "\n\n".join(clean_deep_sections))

    optional_section = build_optional_analysis_section(optional_points)
    if optional_section:
        sections.append(optional_section)

    return "\n\n".join(section for section in sections if section).strip()


def _normalize_point_defaults(point: FocalPoint) -> None:
    mode = str(point.get("generation_mode") or "").strip().upper()
    if mode not in _VALID_GENERATION_MODES:
        strategy = point.get("strategy")
        if strategy == "FLASH_NEWS":
            mode = BRIEF_ONLY
        elif point.get("why_expand"):
            mode = OPTIONAL_DEEP
        else:
            mode = AUTO_DEEP
    point["generation_mode"] = mode

    if not point.get("brief_summary"):
        point["brief_summary"] = str(point.get("topic") or "").strip()

    if mode == OPTIONAL_DEEP and not point.get("why_expand"):
        point["why_expand"] = _fallback_why_expand(point)

    if mode == AUTO_DEEP and not point.get("deep_analysis_reason"):
        point["deep_analysis_reason"] = str(point.get("reasoning") or "").strip()


def _is_auto_deep(point: FocalPoint) -> bool:
    mode = str(point.get("generation_mode") or "").strip().upper()
    if not mode:
        return True
    return mode == AUTO_DEEP


def _fallback_why_expand(point: FocalPoint) -> str:
    topic = str(point.get("topic") or "This topic").strip()
    reasoning = str(point.get("reasoning") or "").strip()
    if reasoning:
        return f"Unresolved strategic impact: {reasoning}"
    return f"{topic} has unresolved strategic implications for today's brief."
