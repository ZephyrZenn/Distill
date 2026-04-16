from __future__ import annotations

from copy import deepcopy
from difflib import SequenceMatcher
import re

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
_MODE_RANK = {BRIEF_ONLY: 0, OPTIONAL_DEEP: 1, AUTO_DEEP: 2}
_OVERLAP_STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "onto",
    "over",
    "under",
    "about",
    "topic",
    "story",
    "news",
    "update",
    "updates",
    "shift",
    "changed",
    "changes",
    "impact",
    "strategic",
    "same",
    "market",
    "value",
    "explain",
    "affect",
    "affects",
    "decision",
    "decisions",
    "happened",
    "shock",
}


def normalize_plan_layers(plan: AgentPlanResult) -> AgentPlanResult:
    normalized = deepcopy(plan)
    if "today_pattern" not in normalized:
        normalized["today_pattern"] = normalized.get("daily_overview", "")

    focal_points = sorted(
        _validate_focal_points(normalized),
        key=lambda point: point["priority"],
    )
    focal_points = _normalize_topic_overlap(focal_points)
    normalized["focal_points"] = focal_points

    auto_deep_count = 0
    for point in focal_points:
        point["brief_summary"] = _optional_text(point, "brief_summary") or point["topic"]
        generation_mode = _normalize_generation_mode(point)
        point["generation_mode"] = generation_mode

        if generation_mode == AUTO_DEEP:
            point["deep_analysis_reason"] = (
                _optional_text(point, "deep_analysis_reason")
                or _optional_text(point, "reasoning")
            )
            if auto_deep_count == 0 or (
                auto_deep_count == 1 and _allows_second_auto_deep(point)
            ):
                auto_deep_count += 1
            else:
                why_expand = _concrete_auto_demotion_reason(point)
                if why_expand:
                    point["generation_mode"] = OPTIONAL_DEEP
                    point["why_expand"] = why_expand
                else:
                    point["generation_mode"] = BRIEF_ONLY
                    point["why_expand"] = ""

        if point["generation_mode"] == OPTIONAL_DEEP:
            if not _is_concrete_why_expand(_optional_text(point, "why_expand")):
                point["generation_mode"] = BRIEF_ONLY
                point["why_expand"] = ""

    return normalized


def _normalize_topic_overlap(focal_points: list[FocalPoint]) -> list[FocalPoint]:
    merged: list[FocalPoint] = []

    for point in focal_points:
        target = _find_overlapping_point(merged, point)
        if target is None:
            merged.append(point)
        else:
            _merge_point(target, point)

    budgeted = merged[:_focal_point_ceiling(_unique_article_count(merged))]
    for index, point in enumerate(budgeted, 1):
        point["priority"] = index
    return budgeted


def _find_overlapping_point(
    candidates: list[FocalPoint],
    point: FocalPoint,
) -> FocalPoint | None:
    for candidate in candidates:
        if (
            _article_overlap(candidate, point) >= 0.5
            or _topic_similarity(candidate, point) >= 0.72
            or _implication_similarity(candidate, point) >= 0.5
        ):
            return candidate
    return None


def _merge_point(target: FocalPoint, source: FocalPoint) -> None:
    target["article_ids"] = _merge_article_ids(
        target.get("article_ids", []),
        source.get("article_ids", []),
    )

    target_mode = _normalize_generation_mode(target)
    source_mode = _normalize_generation_mode(source)
    if _MODE_RANK[source_mode] > _MODE_RANK[target_mode]:
        target["generation_mode"] = source_mode

    for field in ("why_expand", "deep_analysis_reason", "auto_deep_exception"):
        if not _optional_text(target, field) and _optional_text(source, field):
            target[field] = source[field]

    if _optional_text(source, "reasoning"):
        target_reasoning = _optional_text(target, "reasoning")
        source_reasoning = _optional_text(source, "reasoning")
        if source_reasoning not in target_reasoning:
            target["reasoning"] = (
                f"{target_reasoning} / {source_reasoning}"
                if target_reasoning
                else source_reasoning
            )


def _merge_article_ids(first: object, second: object) -> list[str]:
    merged: list[str] = []
    for article_id in list(first or []) + list(second or []):
        text_id = str(article_id)
        if text_id not in merged:
            merged.append(text_id)
    return merged


def _article_overlap(first: FocalPoint, second: FocalPoint) -> float:
    first_ids = {str(article_id) for article_id in first.get("article_ids", [])}
    second_ids = {str(article_id) for article_id in second.get("article_ids", [])}
    if not first_ids or not second_ids:
        return 0.0
    return len(first_ids & second_ids) / len(first_ids | second_ids)


def _topic_similarity(first: FocalPoint, second: FocalPoint) -> float:
    first_topic = _normalize_overlap_text(_optional_text(first, "topic"))
    second_topic = _normalize_overlap_text(_optional_text(second, "topic"))
    if not first_topic or not second_topic:
        return 0.0
    return SequenceMatcher(None, first_topic, second_topic).ratio()


def _implication_similarity(first: FocalPoint, second: FocalPoint) -> float:
    first_tokens = _meaningful_tokens(_implication_text(first))
    second_tokens = _meaningful_tokens(_implication_text(second))
    if len(first_tokens) < 4 or len(second_tokens) < 4:
        return 0.0
    shared_tokens = first_tokens & second_tokens
    if len(shared_tokens) < 3:
        return 0.0
    return len(shared_tokens) / min(len(first_tokens), len(second_tokens))


def _implication_text(point: FocalPoint) -> str:
    return " ".join(
        _optional_text(point, field)
        for field in (
            "relevance_description",
            "reasoning",
            "writing_guide",
            "brief_summary",
        )
    )


def _meaningful_tokens(text: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) >= 4 and token not in _OVERLAP_STOP_WORDS
    }


def _normalize_overlap_text(text: str) -> str:
    return " ".join(sorted(_meaningful_tokens(text)))


def _unique_article_count(focal_points: list[FocalPoint]) -> int:
    return len(
        {
            str(article_id)
            for point in focal_points
            for article_id in point.get("article_ids", [])
        }
    )


def _focal_point_ceiling(article_count: int) -> int:
    if article_count <= 10:
        return 3
    if article_count <= 20:
        return 4
    return 5


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

    lines: list[str] = []
    for point in points:
        topic = _optional_text(point, "topic") or "Optional Topic"
        brief_summary = _optional_text(point, "brief_summary") or point["topic"]
        why_expand = _optional_text(point, "why_expand")
        lines.append(f"## {topic}")
        lines.append(brief_summary)
        if why_expand:
            lines.append(f"\nWhy expand: {why_expand}")
    return "\n".join(lines)


def assemble_layered_report(
    primary_brief: str,
    deep_sections: list[str],
    optional_points: list[FocalPoint],
) -> str:
    sections = [primary_brief.rstrip()]

    cleaned_deep_sections = [section.strip() for section in deep_sections if section.strip()]
    if cleaned_deep_sections:
        sections.append("\n\n".join(cleaned_deep_sections))

    optional_section = build_optional_analysis_section(optional_points)
    if optional_section:
        sections.append(optional_section)

    return "\n\n".join(section for section in sections if section).rstrip()


def _normalize_generation_mode(point: FocalPoint) -> GenerationMode:
    generation_mode = _optional_text(point, "generation_mode")
    if generation_mode in _VALID_GENERATION_MODES:
        return generation_mode
    if point.get("strategy") == "FLASH_NEWS":
        return BRIEF_ONLY
    return OPTIONAL_DEEP


def _allows_second_auto_deep(point: FocalPoint) -> bool:
    exception = _optional_text(point, "auto_deep_exception")
    lowered = exception.lower()
    return (
        len(exception) >= 40
        and "independent" in lowered
        and ("cannot be merged" in lowered or "cannot merge" in lowered)
    )


def _validate_focal_points(plan: AgentPlanResult) -> list[FocalPoint]:
    focal_points = plan.get("focal_points", [])
    if not isinstance(focal_points, list):
        raise ValueError("focal_points must be a list")

    for index, point in enumerate(focal_points):
        if not isinstance(point, dict):
            raise ValueError(f"focal_points[{index}] must be an object")
        for field in ("topic", "strategy", "priority"):
            if field not in point:
                raise ValueError(f"focal_points[{index}] missing required field: {field}")
        point["priority"] = _validate_priority(point["priority"], index)

    return focal_points


def _validate_priority(priority: object, index: int) -> int:
    if isinstance(priority, bool) or not isinstance(priority, int):
        raise ValueError(f"focal_points[{index}] priority must be an integer") from None
    return priority


def _concrete_auto_demotion_reason(point: FocalPoint) -> str:
    for reason in (
        _optional_text(point, "deep_analysis_reason"),
        _optional_text(point, "reasoning"),
    ):
        if _is_concrete_why_expand(reason):
            return reason
    return ""


def _optional_text(point: FocalPoint, field: str) -> str:
    value = point.get(field, "")
    if isinstance(value, str):
        return value
    return ""


def _is_concrete_why_expand(reason: object) -> bool:
    if not isinstance(reason, str):
        return False

    text = reason.strip()
    if not text or len(text) < 20:
        return False

    lowered = text.lower()
    normalized = lowered.strip(" .。!！,，")
    if normalized in _VAGUE_REASONS:
        return False

    return any(marker in lowered for marker in _CONCRETE_MARKERS)
