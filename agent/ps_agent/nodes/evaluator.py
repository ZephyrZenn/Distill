"""Execution, writing, review, and routing logic for the agentic workflow."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from agent.models import WritingMaterial
from agent.tools.writing_tool import review_article, write_article
from agent.utils import extract_json
from core.llm_client import LLMClient
from core.models.llm import Message

from ..prompts import WRITER_SYSTEM_PROMPT
from ..state import PSAgentState, ResearchItem, log_step
from ..tools import execute_tool_calls

logger = logging.getLogger(__name__)

WRITER_MAX_ITEMS = 30


# ---------------------------------------------------------------------------
# Tool execution node
# ---------------------------------------------------------------------------


class ToolExecutorNode:
    """Execute tool calls from the most recent assistant message."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        tool_calls = _last_tool_calls(state)
        if not tool_calls:
            return {
                **log_step(state, "ℹ️ tooling: 未检测到工具调用，继续研究/写作"),
                "status": "researching",
                "messages": [Message.assistant("未检测到工具调用，继续研究或进入写作。")],
            }

        logger.info(
            "[tools] run_id=%s executing=%d tool_call_count=%s",
            run_id,
            len(tool_calls),
            state.get("tool_call_count", 0),
        )
        try:
            pre = log_step(
                state,
                f"🔧 tooling: 执行工具调用 {len(tool_calls)} 个: "
                + ",".join(tc.name for tc in tool_calls),
            )
            updates = await execute_tool_calls(state, tool_calls)
            updates.setdefault("status", "researching")
            updates = {**pre, **updates}
            return updates
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("[tools] execution failed")
            return {
                **log_step(state, f"❌ tooling: 工具执行失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
                "messages": [Message.assistant(f"工具执行失败：{exc}")],
            }





class ReviewerNode:
    """Review the draft and decide whether to refine or continue research."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        draft = state.get("draft_report")
        if not draft:
            return {
                **log_step(state, "❌ reviewing: draft_report 为空，无法审稿"),
                "status": "failed",
                "last_error": "draft_report 为空",
                "messages": [Message.assistant("无法审稿：没有草稿内容。")],
            }

        material = _build_writing_material(state)

        try:
            pre = log_step(state, "🧪 reviewing: 开始审稿")
            review = await review_article(self.client, draft, material)
            logger.info(
                "[review] run_id=%s status=%s score=%s missing_info=%d",
                run_id,
                review.get("status"),
                review.get("score"),
                len(review.get("missing_info") or []),
            )
            return {
                **pre,
                **log_step(
                    state,
                    f"🧪 reviewing: 完成 status={review.get('status')} score={review.get('score')}",
                ),
                "review_result": review,
                "status": "reviewing",
                "last_error": None,
                "messages": [
                    Message.assistant(
                        f"审稿完成：status={review.get('status')} score={review.get('score')}"
                    )
                ],
            }
        except Exception as exc:
            logger.exception("[review] failed")
            return {
                **log_step(state, f"❌ reviewing: 审稿失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
                "messages": [Message.assistant(f"审稿阶段失败：{exc}")],
            }


class RefinerNode:
    """Refine the draft using review feedback (no new tool calls)."""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        review = state.get("review_result") or {}
        material = _build_writing_material(state)

        if state.get("refine_count", 0) >= state.get("max_refine", 0):
            logger.warning("[refine] refine budget exhausted")
            return {
                "status": "completed",
                "final_report": state.get("draft_report"),
                "messages": [Message.assistant("达到修订上限，使用当前草稿作为最终结果。")],
            }

        try:
            pre = log_step(
                state,
                f"🧩 refining: 根据审稿意见修订 (refine_count={state.get('refine_count', 0) + 1})",
            )
            refined = await write_article(self.client, material, review=review)
            logger.info("[refine] run_id=%s refine_count=%s refined_chars=%d", run_id, state.get("refine_count", 0) + 1, len(refined or ""))
            return {
                **pre,
                **log_step(state, f"🧩 refining: 修订完成 (chars={len(refined or '')})"),
                "draft_report": refined,
                "refine_count": state.get("refine_count", 0) + 1,
                "status": "reviewing",
                "last_error": None,
                "messages": [Message.assistant("已根据审稿意见完成一次修订，重新审稿。")],
            }
        except Exception as exc:  # pragma: no cover - defensive
            logger.exception("[refine] failed")
            return {
                **log_step(state, f"❌ refining: 修订失败: {exc}"),
                "status": "failed",
                "last_error": str(exc),
                "messages": [Message.assistant(f"修订阶段失败：{exc}")],
            }


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------


def research_router(state: PSAgentState) -> Literal["tooling", "writing", "researching"]:
    """Route after a research iteration."""
    run_id = state.get("run_id", "-")
    if state.get("status") == "failed":
        logger.info("[route] run_id=%s research_router=writing reason=failed", run_id)
        return "writing"

    if state["iteration"] >= state["max_iterations"]:
        logger.info("[route] run_id=%s research_router=writing reason=max_iterations", run_id)
        return "writing"

    if state["tool_call_count"] >= state["max_tool_calls"]:
        logger.info("[route] run_id=%s research_router=writing reason=max_tool_calls", run_id)
        return "writing"

    tool_calls = _last_tool_calls(state)
    if tool_calls:
        logger.info("[route] run_id=%s research_router=tooling reason=has_tool_calls count=%d", run_id, len(tool_calls))
        return "tooling"

    last_content = _last_assistant_content(state)
    if last_content.upper().startswith("READY_TO_WRITE"):
        logger.info("[route] run_id=%s research_router=writing reason=ready_to_write", run_id)
        return "writing"

    # Default: keep researching.
    logger.info("[route] run_id=%s research_router=researching reason=default", run_id)
    return "researching"


def curation_router(state: PSAgentState) -> Literal["writing", "research"]:
    """Route after curation.

    If the model explicitly called `finish_research`, we keep curation in the loop
    (for dedup/bounding) and then proceed to writing.
    """
    if state.get("ready_to_write"):
        return "writing"
    return "research"


def review_router(state: PSAgentState) -> Literal["completed", "refining", "researching"]:
    """Route after reviewing a draft."""
    run_id = state.get("run_id", "-")
    review = state.get("review_result") or {}
    status = str(review.get("status", "")).upper()
    missing_info = review.get("missing_info") or []

    if status == "APPROVED":
        logger.info("[route] run_id=%s review_router=completed reason=approved", run_id)
        return "completed"

    # If the reviewer explicitly says we are missing key info, try one more research loop.
    if missing_info and state["iteration"] < state["max_iterations"] and state["tool_call_count"] < state["max_tool_calls"]:
        logger.info("[route] run_id=%s review_router=researching reason=missing_info count=%d", run_id, len(missing_info))
        return "researching"

    if state.get("refine_count", 0) < state.get("max_refine", 0):
        logger.info("[route] run_id=%s review_router=refining reason=within_refine_budget", run_id)
        return "refining"

    logger.info("[route] run_id=%s review_router=completed reason=budget_exhausted", run_id)
    return "completed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _last_tool_calls(state: PSAgentState):
    for message in reversed(state.get("messages", [])):
        if message.role == "assistant" and message.tool_calls:
            return message.tool_calls
        if message.role == "assistant":
            return []
    return []


def _last_assistant_content(state: PSAgentState) -> str:
    for message in reversed(state.get("messages", [])):
        if message.role == "assistant":
            return message.content or ""
    return ""


def _parse_pub_date(value: str | None) -> datetime:
    if not value:
        return datetime.now()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now()


def _article_summary(item: ResearchItem, *, limit: int = 400) -> str:
    summary = str(item.get("summary", "") or "").strip()
    if summary:
        return summary[:limit]
    content = str(item.get("content", "") or "").strip()
    if not content:
        return ""
    return content[:limit] + ("..." if len(content) > limit else "")


def _select_top_items_for_writer(
    items: list[ResearchItem], limit: int = WRITER_MAX_ITEMS
) -> list[ResearchItem]:
    if not items:
        return []
    scored = []
    for item in items:
        score = float(item.get("score", 0.0) or 0.0)
        published_at = str(item.get("published_at", "") or "")
        try:
            dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
            recency_ts = dt.timestamp()
        except Exception:
            recency_ts = 0.0
        scored.append((score, recency_ts, item))

    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return [item for _, __, item in scored[:limit]]


def _build_writing_material(state: PSAgentState) -> WritingMaterial:
    focus = state["focus"]
    items = _select_top_items_for_writer(list(state.get("research_items", [])))

    # Inline construction logic replacing PSWritingMaterial
    articles: list[dict] = []
    ext_info: list[dict] = []
    memories: list[dict] = []
    
    # Process items (simplified from PSWritingMaterial)
    for item in items:
        src = str(item.get("source", "") or "")
        # Basic clipping
        summary = str(item.get("summary", "") or "")
        content = str(item.get("content", "") or "")
        display = summary if len(summary) > 0 else (content[:400] + "..." if len(content) > 400 else content)
        
        record = {
            "id": str(item.get("id", "") or item.get("url", "") or item.get("title", "")),
            "title": str(item.get("title", "") or ""),
            "url": str(item.get("url", "") or ""),
            "summary": display,
            "pub_date": str(item.get("published_at", "")),
            "content": content,
        }
        
        if src == "web":
            ext_info.append(record)
        elif src == "memory":
            memories.append({
                "id": record["id"],
                "topic": record["title"],
                "reasoning": record["summary"],
                "content": content,
            })
        else:
            articles.append(record)

    # Citations
    citations = state.get("citations", [])[:20]
    citation_lines = []
    if citations:
        citation_lines = ["\n可用来源（节选）："]
        for c in citations:
            title = c.get("title", "")
            url = c.get("url", "")
            published_at = c.get("published_at", "")
            citation_lines.append(f"- {title} | {published_at} | {url}")

    # Inject Bucket Context (P1 Feature: Structured Output)
    buckets = state.get("focus_buckets", [])
    bucket_map = {b["id"]: b["name"] for b in buckets}
    
    # Group items by bucket
    grouped_context = {}
    for item in items:
        tags = item.get("tags", [])
        bid = next((t.split("bucket:")[1] for t in tags if t.startswith("bucket:")), None)
        if bid and bid in bucket_map:
            name = bucket_map[bid]
            if name not in grouped_context:
                grouped_context[name] = []
            title = str(item.get("title", ""))
            grouped_context[name].append(f"- {title} (ID: {item.get('id')})")
            
    # Format bucket instructions
    bucket_instructions = []
    if grouped_context:
        bucket_instructions.append("\n## 维度素材映射 (Context Mapping)")
        for name, titles in grouped_context.items():
            bucket_instructions.append(f"### {name}:")
            bucket_instructions.extend(titles)
            
    final_instructions = "\n".join(bucket_instructions)

    guide_lines = [
        WRITER_SYSTEM_PROMPT.strip(),
        f"\n额外要求：\n- 强调近 24 小时变化\n- 关键判断尽量给出来源线索\n- 不确定的地方要标注不确定性\n- 禁止逐条复述素材，必须归纳总结{final_instructions}",
    ] + citation_lines
    
    writing_guide = "\n\n".join(guide_lines)

    return WritingMaterial(
        topic=focus,
        style="DEEP",
        match_type="FOCUS_MATCH",
        relevance_to_focus=f"围绕用户关注点：{focus}",
        writing_guide=writing_guide,
        reasoning="基于规划与研究素材生成结论与影响分析",
        articles=articles,
        ext_info=ext_info,
        history_memory=memories,
    )


# LangGraph wiring helpers ---------------------------------------------------

_tool_node: ToolExecutorNode | None = None
_reviewer_node: ReviewerNode | None = None
_refiner_node: RefinerNode | None = None


def set_evaluator_client(client: LLMClient) -> None:
    global _tool_node, _writer_node, _reviewer_node, _refiner_node
    _tool_node = ToolExecutorNode(client)
    _reviewer_node = ReviewerNode(client)
    _refiner_node = RefinerNode(client)


async def tool_node(state: PSAgentState) -> dict:
    if _tool_node is None:  # pragma: no cover - defensive
        raise RuntimeError("Evaluator client not initialized. Call set_evaluator_client first.")
    return await _tool_node(state)


async def evaluator_node(state: PSAgentState) -> dict:
    """Backwards-compatible name: we treat evaluator as the reviewer."""
    if _reviewer_node is None:  # pragma: no cover - defensive
        raise RuntimeError("Evaluator client not initialized. Call set_evaluator_client first.")
    return await _reviewer_node(state)





async def reviewer_node(state: PSAgentState) -> dict:
    return await evaluator_node(state)


async def refiner_node(state: PSAgentState) -> dict:
    if _refiner_node is None:  # pragma: no cover - defensive
        raise RuntimeError("Evaluator client not initialized. Call set_evaluator_client first.")
    return await _refiner_node(state)


__all__ = [
    "evaluator_node",
    "research_router",
    "review_router",
    "set_evaluator_client",
    "tool_node",
    "reviewer_node",
    "refiner_node",
]
