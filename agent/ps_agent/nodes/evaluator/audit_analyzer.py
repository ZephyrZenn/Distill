"""Audit feedback analysis for search guidance."""

from __future__ import annotations

import logging

from core.models.llm import Message
from agent.utils import extract_json
from core.llm_client import LLMClient
from agent.ps_agent.models import Dimension, AuditAnalysisResult, ResearchItem
from agent.ps_agent.prompts import AUDIT_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)


class AuditAnalyzer:
    """Analyzes audit results to generate feedback and search pivots.

    Args:
        client: LLM client for generating search pivots
    """

    def __init__(self, client: LLMClient) -> None:
        self.client = client

    async def analyze_with_spiral_guidance(
        self,
        kept_items: list[ResearchItem],
        discarded_items: list[ResearchItem],
        focus: str,
        focus_dimensions: list[Dimension],
        query_history: list[dict],
        current_date: str,
    ) -> AuditAnalysisResult:
        """Extended analysis with spiral-specific guidance (P1 feature).

        Args:
            kept_items: Items that passed audit
            discarded_items: Items that failed audit
            focus: Research focus topic
            focus_dimensions: Research intent dimensions
            query_history: Recent query history
            current_date: Current date
        Returns:
            AuditAnalysisResult with query suggestions and dimension coverage
        """
        discarded_reasons = [item.get("audit_reason", "") for item in discarded_items]
        # history_queries = [item.get("query", "") for item in query_history]
        kept_info = [{
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "summary": item.get("summary", ""),
            "relevance": item.get("relevance", 0),
            "audit_reason": item.get("audit_reason", ""),
        } for item in kept_items]
        prompt_sections = []
        prompt_sections.append(f"当前日期: {current_date}\n\n")
        prompt_sections.append(f"研究主题: {focus}\n\n")
        prompt_sections.append(f"研究意图维度: {focus_dimensions}\n\n")
        prompt_sections.append(f"已有素材: {kept_info}\n\n")
        prompt_sections.append(f"本轮搜索丢弃的垃圾素材的丢弃原因: {discarded_reasons}\n\n")
        prompt_sections.append(f"查询历史: {query_history}\n\n")
        user_prompt = "\n".join(prompt_sections)
        messages = [
            Message.system(AUDIT_ANALYSIS_PROMPT),
            Message.user(user_prompt),
        ]
        response = await self.client.completion(
            messages,
            json_format=True,
        )
        result = extract_json(response)
        return result
        

    def _detect_repeat_patterns(
        self,
        discarded_items: list[ResearchItem],
        query_history: list[dict],
    ) -> bool:
        """Detect if searches are repeating without progress.

        Args:
            discarded_items: Items that were discarded
            query_history: Recent query history

        Returns:
            True if repeat pattern detected, False otherwise
        """
        # Simple heuristic: if we have many discarded items with low relevance
        # and recent queries show similarity, it's a repeat pattern
        if len(discarded_items) < 5:
            return False

        low_relevance_count = sum(
            1 for item in discarded_items if item.get("llm_relevance", 0) < 0.4
        )

        # If >70% of discarded items have low relevance, we're stuck
        if low_relevance_count > len(discarded_items) * 0.7:
            return True

        return False


__all__ = ["AuditAnalyzer"]
