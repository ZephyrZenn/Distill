from __future__ import annotations

from copy import deepcopy

from agent.models import AgentPlanResult, FocalPoint, GenerationMode

BRIEF_ONLY: GenerationMode = "BRIEF_ONLY"
OPTIONAL_DEEP: GenerationMode = "OPTIONAL_DEEP"
AUTO_DEEP: GenerationMode = "AUTO_DEEP"

_VALID_GENERATION_MODES = {BRIEF_ONLY, OPTIONAL_DEEP, AUTO_DEEP}
_VAGUE_REASONS = {
    "important topic",
    "worth watching",
    "has impact",
    "值得关注",
    "很重要",
    "影响很大",
}
_CONCRETE_MARKERS = (
    "uncertainty",
    "uncertain",
    "unresolved",
    "conflict",
    "conflicting",
    "timing",
    "downstream",
    "strategic",
    "impact",
    "budget",
    "cost",
    "risk",
    "roadmap",
    "不确定",
    "未解决",
    "冲突",
    "时机",
    "时间",
    "下游",
    "战略",
    "影响",
    "预算",
    "成本",
    "风险",
    "路线图",
)


def normalize_plan_layers(plan: AgentPlanResult) -> AgentPlanResult:
    normalized = deepcopy(plan)
    if "today_pattern" not in normalized:
        normalized["today_pattern"] = normalized.get("daily_overview", "")

    focal_points = sorted(
        normalized.get("focal_points", []),
        key=lambda point: point.get("priority", 0),
    )
    normalized["focal_points"] = focal_points

    auto_deep_count = 0
    for point in focal_points:
        point["brief_summary"] = point.get("brief_summary") or point["topic"]
        generation_mode = _normalize_generation_mode(point)
        point["generation_mode"] = generation_mode

        if generation_mode == AUTO_DEEP:
            point["deep_analysis_reason"] = (
                point.get("deep_analysis_reason") or point.get("reasoning", "")
            )
            if auto_deep_count == 0 or (
                auto_deep_count == 1 and _allows_second_auto_deep(point)
            ):
                auto_deep_count += 1
            else:
                point["generation_mode"] = OPTIONAL_DEEP
                point["why_expand"] = _fallback_why_expand(point)

        if point["generation_mode"] == OPTIONAL_DEEP:
            point["why_expand"] = point.get("why_expand") or _fallback_why_expand(point)
            if not _is_concrete_why_expand(point["why_expand"]):
                point["generation_mode"] = BRIEF_ONLY
                point["why_expand"] = ""

    return normalized


def get_auto_deep_points(plan: AgentPlanResult) -> list[FocalPoint]:
    return [
        point
        for point in plan.get("focal_points", [])
        if point.get("generation_mode") == AUTO_DEEP
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

    lines = ["## Optional Analysis"]
    for point in points:
        brief_summary = point.get("brief_summary") or point["topic"]
        why_expand = point.get("why_expand", "")
        lines.append(f"- {brief_summary} Why expand: {why_expand}")
    return "\n".join(lines)


def assemble_layered_report(
    primary_brief: str,
    deep_sections: list[str],
    optional_points: list[FocalPoint],
) -> str:
    sections = [primary_brief.rstrip()]

    cleaned_deep_sections = [section.strip() for section in deep_sections if section.strip()]
    if cleaned_deep_sections:
        sections.append("## Deep Analysis\n\n" + "\n\n".join(cleaned_deep_sections))

    optional_section = build_optional_analysis_section(optional_points)
    if optional_section:
        sections.append(optional_section)

    return "\n\n".join(section for section in sections if section).rstrip()


def _normalize_generation_mode(point: FocalPoint) -> GenerationMode:
    generation_mode = point.get("generation_mode")
    if generation_mode in _VALID_GENERATION_MODES:
        return generation_mode
    if point.get("strategy") == "FLASH_NEWS":
        return BRIEF_ONLY
    return OPTIONAL_DEEP


def _allows_second_auto_deep(point: FocalPoint) -> bool:
    exception = point.get("auto_deep_exception", "")
    lowered = exception.lower()
    return (
        len(exception) >= 40
        and "independent" in lowered
        and ("cannot be merged" in lowered or "cannot merge" in lowered)
    )


def _fallback_why_expand(point: FocalPoint) -> str:
    reason = point.get("deep_analysis_reason") or point.get("reasoning", "")
    topic = point.get("topic", "this topic")
    if _is_concrete_why_expand(reason):
        return reason
    if reason:
        return (
            f"{reason} Further analysis of {topic} could clarify downstream "
            "strategic impact."
        )
    return (
        f"Unresolved questions about {topic} could affect strategic impact "
        "and downstream decisions."
    )


def _is_concrete_why_expand(reason: str) -> bool:
    text = reason.strip()
    if not text or len(text) < 24:
        return False

    lowered = text.lower()
    normalized = lowered.strip(" .。!！,，")
    if normalized in _VAGUE_REASONS:
        return False

    return any(marker in lowered for marker in _CONCRETE_MARKERS)
