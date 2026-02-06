"""Batch LLM audit orchestration for material curation."""

from __future__ import annotations

import json
import logging
from core.llm_client import LLMClient

from agent.ps_agent.models import SnippetAuditResult, ResearchItem, Dimension
from core.models.llm import Message
from agent.ps_agent.audit.batch_processor import BatchProcessor
from agent.ps_agent.audit.result_parser import parse_audit_result
from agent.ps_agent.prompts.snippet_audit import SNIPPET_AUDIT_PROMPT
from agent.ps_agent.prompts.full_audit import FULL_AUDIT_PROMPT
from agent.utils import extract_json

logger = logging.getLogger(__name__)


class BatchAuditor:
    """Orchestrates batch LLM audit in two stages.

    Args:
        client: LLM client for making API calls
        batch_size: Number of items per batch (default: 15)
    """

    def __init__(self, client: LLMClient, batch_size: int = 15) -> None:
        self.client = client
        self.batch_processor = BatchProcessor(batch_size)

    async def audit_stage1_snippet(
        self,
        items: list[ResearchItem],
        focus: str,
        focus_dimensions: list[Dimension] | list[dict],
        current_date: str,
    ) -> tuple[list[ResearchItem], list[ResearchItem], dict]:
        """Stage 1: Fast snippet-based audit.

        Args:
            items: Research items to audit
            focus: Research focus topic
            focus_dimensions: List of focus dimensions
            current_date: Current date
        Returns:
            Tuple of (kept_items, discarded_items, metadata)
        """
        logger.info(f"[audit:stage1] Starting snippet audit for {len(items)} items")

        kept = []
        discarded = []
        metadata = {
            "stage": "snippet",
            "total_audited": len(items),
            "llm_calls": 0,
            "token_estimate": 0,
        }

        # Split into batches
        batches = self.batch_processor.create_batches(items)

        for batch_idx, batch in enumerate(batches):
            logger.info(
                f"[audit:stage1] Processing batch {batch_idx + 1}/{len(batches)} "
                f"(size={len(batch)})"
            )

            try:
                result = await self._call_snippet_audit_llm(batch, focus, focus_dimensions, current_date)
                metadata["llm_calls"] += 1

                kept_batch, discarded_batch = parse_audit_result(batch, result, stage="snippet")

                kept.extend(kept_batch)
                discarded.extend(discarded_batch)

            except Exception as e:
                logger.error(f"[audit:stage1] Batch {batch_idx} failed: {e}", exc_info=True)
                # Fallback: keep all items from failed batch
                kept.extend(batch)

        logger.info(
            f"[audit:stage1] Complete: kept={len(kept)}, discarded={len(discarded)}, "
            f"llm_calls={metadata['llm_calls']}"
        )
        return kept, discarded, metadata

    async def audit_stage2_full(
        self,
        items: list[ResearchItem],
        focus: str,
        focus_dimensions: list[dict],
        current_date: str,
    ) -> tuple[list[ResearchItem], list[ResearchItem], dict]:
        """Stage 2: Deep full-content audit.

        Args:
            items: Research items marked for full audit (should_fetch_full=True)
            focus: Research focus topic
            focus_dimensions: List of focus dimensions
            current_date: Current date
        Returns:
            Tuple of (kept_items, discarded_items, metadata)
        """
        logger.info(f"[audit:stage2] Starting full audit for {len(items)} items")

        kept = []
        discarded = []
        metadata = {
            "stage": "full",
            "total_audited": len(items),
            "llm_calls": 0,
        }

        # TODO: don't use magic number here.
        batch_size = 5
        batches = self.batch_processor.create_batches_with_size(items, batch_size)

        for batch_idx, batch in enumerate(batches):
            logger.info(
                f"[audit:stage2] Processing batch {batch_idx + 1}/{len(batches)} "
                f"(size={len(batch)})"
            )

            try:
                result = await self._call_full_audit_llm(
                    batch, focus, focus_dimensions, current_date
                )
                metadata["llm_calls"] += 1

                kept_batch, discarded_batch = parse_audit_result(batch, result, stage="full")

                kept.extend(kept_batch)
                discarded.extend(discarded_batch)

            except Exception as e:
                logger.error(f"[audit:stage2] Batch {batch_idx} failed: {e}", exc_info=True)
                kept.extend(batch)

        logger.info(
            f"[audit:stage2] Complete: kept={len(kept)}, discarded={len(discarded)}, "
            f"llm_calls={metadata['llm_calls']}"
        )
        return kept, discarded, metadata

    async def _call_snippet_audit_llm(
        self,
        batch: list[ResearchItem],
        focus: str,
        focus_dimensions: list[Dimension] | list[dict],
        current_date: str,
    ) -> list[SnippetAuditResult]:
        """Call LLM for snippet audit.

        Args:
            batch: Batch of research items
            focus: Research focus topic
            focus_dimensions: List of focus dimensions (Dimension objects or dicts)
            current_date: Current date
        Returns:
            Parsed JSON response from LLM
        """
        # Prepare batch items for prompt
        items_json = self._format_items_for_audit(batch, include_content=False)

        # Build dimension context
        dimensions_context = self._format_dimensions(focus_dimensions)

        user_prompt = f"""Please audit the following research materials.
current date: {current_date}

## Research Focus
{focus}

## Key Dimensions
{dimensions_context}

## Research Materials ({len(batch)} items)
```json
{items_json}
```

Return audit results in JSON format.
"""

        messages = [
            Message.system(SNIPPET_AUDIT_PROMPT),
            Message.user(user_prompt),
        ]

        response = await self.client.completion(messages)
        res = extract_json(response)
        return res["results"]

    async def _call_full_audit_llm(
        self,
        batch: list[ResearchItem],
        focus: str,
        focus_dimensions: list[Dimension] | list[dict],
        current_date: str,
    ) -> dict:
        """Call LLM for full content audit.

        Args:
            batch: Batch of research items
            focus: Research focus topic
            focus_dimensions: List of focus dimensions (Dimension objects or dicts)
            current_date: Current date
        Returns:
            Parsed JSON response from LLM
        """
        items_json = self._format_items_for_audit(batch, include_content=True)
        dimensions_context = self._format_dimensions(focus_dimensions)

        user_prompt = f"""Please perform deep audit on the following research materials.
current date: {current_date}
## Research Focus
{focus}

## Key Dimensions
{dimensions_context}

## Research Materials ({len(batch)} items)
```json
{items_json}
```

Return audit results in JSON format.
"""

        messages = [
            Message.system(FULL_AUDIT_PROMPT),
            Message.user(user_prompt),
        ]

        response = await self.client.completion(messages)
        res = extract_json(response)
        return res["results"]

    def _format_items_for_audit(
        self, items: list[ResearchItem], include_content: bool = False
    ) -> str:
        """Format items for LLM prompt.

        Args:
            items: List of research items
            include_content: Whether to include full content

        Returns:
            JSON string of formatted items
        """
        formatted = []
        for item in items:
            item_dict = {
                "id": item["id"],
                "title": item.get("title", "")[:200],
                "summary": item.get("summary", "")[:800],
                "source": item.get("source", ""),
                "published_at": item.get("published_at", ""),
            }

            if include_content and item.get("content"):
                # Truncate full content to avoid token overflow
                item_dict["content"] = item["content"][:3000]

            formatted.append(item_dict)

        return json.dumps(formatted, ensure_ascii=False, indent=2)

    def _format_dimensions(self, dimensions: list) -> str:
        """Format focus dimensions for prompt.

        只传递意图描述，不传递额外的关键词，让 LLM 专注于理解研究意图。

        Args:
            dimensions: List of Dimension objects or dicts

        Returns:
            Formatted string of dimensions
        """
        if not dimensions:
            return "No specific dimensions"

        lines = []
        for dim in dimensions[:5]:  # Limit to top 5 dimensions
            # Handle both Dimension objects and dicts
            if hasattr(dim, 'name'):
                # Dimension object
                name = dim.name
                intent = dim.intent
                priority = dim.priority
            else:
                # dict
                name = dim.get("name", "")
                intent = dim.get("intent", "")
                priority = dim.get("priority", "medium")
            lines.append(f"- **{name}** (priority={priority}): {intent}")

        return "\n".join(lines)


__all__ = ["BatchAuditor"]
