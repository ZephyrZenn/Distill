"""Curation node: audit research items and determine sufficiency."""

from __future__ import annotations

import logging

from agent.ps_agent.utils.content_fetcher import fetch_contents
from core.llm_client import LLMClient
from core.models.llm import Message

from agent.ps_agent.state import (
    PSAgentState,
    log_step,
)
from agent.tracing import trace_event

# P0: Two-stage LLM audit imports
from agent.ps_agent.nodes.evaluator.batch_audit import BatchAuditor
from agent.ps_agent.nodes.evaluator.audit_analyzer import AuditAnalyzer
from agent.ps_agent.models import ResearchItem, DiscardedItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------


def _is_homepage_url(url: str) -> bool:
    """检测是否为首页 URL（避免收录网站首页而非具体文章）"""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path.strip().rstrip("/")

        # 首页特征检测
        if path in ["", "/"]:
            return True

        path_parts = [p for p in path.split("/") if p]
        if len(path_parts) <= 1:
            if path.lower() in ["home", "index", "index.html", "index.htm"]:
                return True

        if len(path_parts) <= 1:
            news_keywords = [
                "article",
                "news",
                "post",
                "story",
                "blog",
                "press",
                "detail",
            ]
            has_article_keyword = any(kw in path.lower() for kw in news_keywords)
            if not has_article_keyword:
                has_id_pattern = any(
                    part.isdigit() or any(c.isdigit() for c in part)
                    for part in path_parts
                )
                if not has_id_pattern:
                    return True

        return False

    except Exception:
        return False


class MaterialCurationNode:
    """Triage research items and determine if sufficient for review.

    Responsibilities:
    1. Judge article quality (relevance + quality scoring)
    2. Judge material sufficiency after Stage 1
    3. Provide audit feedback to researcher for search improvement
    4. When sufficient: fetch full content, perform Stage 2 audit, and score items

    Two-stage audit:
    - Stage 1 (snippet): Fast evaluation using title + summary, then decide if sufficient
    - Stage 2 (full): Deep evaluation with full content, only when sufficient
    """

    def __init__(self, client: LLMClient, audit_client: LLMClient):
        self.client = client
        self.batch_auditor = BatchAuditor(audit_client, batch_size=15)
        self.audit_analyzer = AuditAnalyzer(client)

    async def __call__(self, state: PSAgentState) -> dict:
        run_id = state.get("run_id", "-")
        items = list(state.get("research_items", []))
        logger.info(
            "[ps_agent] run_id=%s node=curation entry research_items=%d",
            run_id, len(items),
        )
        if not items:
            log_step(state, trace_event("curation.empty"))
            return {
                "status": "researching",
                "ready_for_review": False,
                "curation_count": state.get("curation_count", 0) + 1,
                "messages": [Message.assistant("暂无可筛选素材，继续研究。")],
            }

        log_step(state, trace_event("curation.stage1.start", count=len(items)))
        # Stage 1: Snippet Audit (fast, title + summary only)
        # After Stage 1, decide if sufficient → either continue research or go to Stage 2
        kept_items, discarded_items, audit_analysis = await self._audit_stage1_snippet(
            state, items
        )
        if not audit_analysis or not audit_analysis.get("is_sufficient"):
            log_step(
                state,
                trace_event(
                    "curation.stage1.continue",
                    kept=len(kept_items),
                    discarded=len(discarded_items),
                ),
            )
            return {
                "research_items": kept_items,
                "discarded_items": list(state.get("discarded_items", []))
                + discarded_items,
                "audit_analysis": audit_analysis,
                "status": "research",
                "curation_count": state.get("curation_count", 0) + 1,
                "messages": [
                    Message.assistant(
                        f"Stage 1 审计完成：保留 {len(kept_items)} 条，"
                        f"丢弃 {len(discarded_items)} 条。{audit_analysis.get('reason') if audit_analysis else '审计失败，继续研究。'}"
                    )
                ],
            }

        log_step(state, trace_event("curation.stage2.start", count=len(kept_items)))
        web_contents, feed_contents = await fetch_contents(kept_items)
        for item in kept_items:
            if item.get("source") == "web":
                item["content"] = web_contents.get(item.get("url", ""), "")
            elif item.get("source") == "feed":
                item["content"] = feed_contents.get(item.get("id", ""), "")
        log_step(state, trace_event("curation.content.fetched", count=len(kept_items)))

        # Stage 2: Full Content Audit (deep, with full content)
        # Only executed when materials are confirmed sufficient

        scored_items, discarded, metadata = await self._audit_stage2_full(
            state, kept_items
        )
        log_step(state, trace_event("curation.stage2.scoring", count=len(scored_items)))
        log_step(state, trace_event("curation.completed"))
        return {
            "research_items": scored_items,
            "discarded_items": list(state.get("discarded_items", [])) + discarded,
            "status": "plan_review",
            "ready_for_review": True,
            "curation_count": state.get("curation_count", 0) + 1,
            "messages": [Message.assistant("审计已完成。")],
        }

    async def _audit_stage1_snippet(
        self, state: PSAgentState, items: list[ResearchItem]
    ) -> dict:
        """Stage 1: Fast snippet-based LLM audit.

        Evaluates items using only title + summary to quickly filter out
        irrelevant content. Then analyzes dimension coverage to decide if
        materials are sufficient for Stage 2.

        Flow:
        1. Quick filter items
        2. Run snippet audit
        3. If sufficient: advance to Stage 2
        4. If not sufficient: provide audit_feedback to researcher
        """
        logger.info(f"[curation:stage1] Starting snippet audit for {len(items)} items")

        # Incremental snippet audit:
        # - Items with `snippet_audited=True` will be reused directly
        # - Only new items without this flag go through Stage 1 LLM audit
        already_audited: list[ResearchItem] = []
        new_items_raw: list[ResearchItem] = []
        for item in items:
            if item.get("snippet_audited"):
                already_audited.append(item)
            else:
                new_items_raw.append(item)

        max_keep_items = int(state.get("max_context_items", 15) * 2)

        # If there are no new items to audit, reuse previous analysis and just
        # re-trim existing items by relevance.
        if not new_items_raw:
            logger.info(
                "[curation:stage1] No new items to audit; reusing previous snippet results"
            )
            kept_items = sorted(
                items, key=lambda x: x.get("relevance", 0), reverse=True
            )[:max_keep_items]
            previous_analysis = state.get("audit_analysis")
            return kept_items, [], previous_analysis

        # Apply quick filters before LLM audit for new items only
        filtered_items = await self._quick_filter_items(new_items_raw, state)

        # If all new items are filtered out, keep the already audited items only.
        if not filtered_items:
            logger.info(
                "[curation:stage1] All new items filtered by quick filter; "
                "skipping LLM snippet audit for this round"
            )
            kept_items = sorted(
                already_audited, key=lambda x: x.get("relevance", 0), reverse=True
            )[:max_keep_items]
            previous_analysis = state.get("audit_analysis")
            return kept_items, [], previous_analysis

        # Run LLM snippet audit on new items
        try:
            kept_new, discarded_new, metadata = (
                await self.batch_auditor.audit_stage1_snippet(
                    items=filtered_items,
                    focus=state["focus"],
                    focus_dimensions=state.get("focus_dimensions", []),
                    current_date=state["current_date"],
                )
            )

            # Mark newly audited items
            for item in kept_new:
                item["snippet_audited"] = True
            for item in discarded_new:
                item["snippet_audited"] = True

            # Merge previously audited items with newly kept ones
            merged_kept = already_audited + kept_new
            merged_kept.sort(key=lambda x: x.get("relevance", 0), reverse=True)
            merged_kept = merged_kept[:max_keep_items]

            # Convert discarded items (only newly audited discards) to DiscardedItem
            discarded = [
                DiscardedItem(
                    id=item.get("id", ""),
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    reason=item.get("audit_reason", "LLM snippet audit: discarded"),
                    score=item.get("relevance", 0.0),
                )
                for item in discarded_new
            ]

            logger.info(
                "[curation:stage1] Complete: kept_total=%d (existing=%d, new=%d), "
                "discarded_new=%d, llm_calls=%d",
                len(merged_kept),
                len(already_audited),
                len(kept_new),
                len(discarded),
                metadata.get("llm_calls", 0),
            )

            audit_analysis = await self.audit_analyzer.analyze_with_spiral_guidance(
                kept_items=merged_kept,
                discarded_items=discarded_new,
                focus=state["focus"],
                focus_dimensions=state.get("focus_dimensions", []),
                query_history=state.get("query_history", []),
                current_date=state["current_date"],
            )

            return merged_kept, discarded_new, audit_analysis

        except Exception as e:
            logger.error(f"[curation:stage1] LLM audit failed: {e}", exc_info=True)
            return items, [], None

    async def _audit_stage2_full(
        self, state: PSAgentState, items: list[ResearchItem]
    ) -> dict:
        """Stage 2: Deep full-content LLM audit + scoring.

        This is ONLY executed when materials are confirmed sufficient.
        Fetches full content, performs deep audit, and scores all items.
        After Stage 2, set ready_for_review=True to proceed to plan_review.
        """
        logger.info(f"[curation:stage2] Starting full audit for {len(items)} items")
        max_keep_items = state.get("max_context_items", 15)
        # Run LLM full audit on all items
        try:
            kept_items, discarded_items, metadata = (
                await self.batch_auditor.audit_stage2_full(
                    items=items,
                    focus=state["focus"],
                    focus_dimensions=state.get("focus_dimensions", []),
                    current_date=state["current_date"],
                )
            )

            # Convert discarded items to DiscardedItem format
            discarded = [
                DiscardedItem(
                    id=item.get("id", ""),
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    reason=item.get("audit_reason", "LLM full audit: discarded"),
                    score=item.get("llm_relevance", 0.0),
                )
                for item in discarded_items
            ]

            # Score all items (relevance + quality → composite_score)
            scored_items = self._score_items(kept_items)
            scored_items.sort(key=lambda x: x.get("score", 0), reverse=True)
            scored_items = scored_items[:max_keep_items]
            logger.info(
                "[curation:stage2] Complete: kept=%d, "
                "discarded=%d, "
                "llm_calls=%d, "
                "ready_for_review=True",
                len(scored_items),
                len(discarded),
                metadata.get("llm_calls", 0),
            )

            return scored_items, discarded, metadata

        except Exception as e:
            logger.error(f"[curation:stage2] LLM audit failed: {e}", exc_info=True)
            return items, [], None

    async def _quick_filter_items(
        self, items: list[ResearchItem], state: PSAgentState
    ) -> list[ResearchItem]:
        """Apply quick filters before LLM audit.

        Filters out items that are clearly garbage without LLM call.
        """
        filtered = []

        for item in items:
            # Must have summary
            if not item.get("summary"):
                continue

            # Cannot be homepage URL
            if _is_homepage_url(item.get("url", "")):
                continue

            filtered.append(item)

        logger.info(f"[curation] Quick filter: {len(items)} -> {len(filtered)} items")
        return filtered

    def _score_items(self, items: list[ResearchItem]) -> list[ResearchItem]:
        """Calculate composite scores for research items.

        Uses LLM audit results (llm_relevance + llm_quality) to compute
        composite_score for ranking.

        Args:
            items: Research items with LLM audit results

        Returns:
            Scored research items sorted by composite_score
        """
        scored_items = []
        for item in items:
            relevance = item.get("relevance")
            quality = item.get("quality")
            novelty = item.get("novelty")
            # Calculate composite score from LLM audit results
            composite_score = relevance * 0.5 + quality * 0.3 + novelty * 0.2
            item["score"] = composite_score
            scored_items.append(item)

        # Sort by composite score
        scored_items.sort(key=lambda x: x.get("score", 0), reverse=True)
        avg_score = sum(i.get("score", 0) for i in scored_items) / len(scored_items)
        logger.info(
            f"[curation] Scored {len(scored_items)} items, avg_score={avg_score:.2f}"
        )

        return scored_items
