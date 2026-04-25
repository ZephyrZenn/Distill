"""Batch LLM audit orchestration for material curation."""

from __future__ import annotations

import json
import logging

from core.config import get_config
from core.llm_client import LLMClient
from core.prompt.context_manager import ContextBlock, ContextBudget

from agent.ps_agent.models import Dimension, ResearchItem, SnippetAuditResult
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
                result = await self._call_snippet_audit_llm(
                    batch=batch,
                    focus=focus,
                    focus_dimensions=focus_dimensions,
                    current_date=current_date,
                )
                metadata["llm_calls"] += 1

                kept_batch, discarded_batch = parse_audit_result(
                    batch, result, stage="snippet"
                )

                kept.extend(kept_batch)
                discarded.extend(discarded_batch)

            except Exception as e:
                logger.error(
                    f"[audit:stage1] Batch {batch_idx} failed: {e}", exc_info=True
                )
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
                    batch=batch,
                    focus=focus,
                    focus_dimensions=focus_dimensions,
                    current_date=current_date,
                )
                metadata["llm_calls"] += 1

                kept_batch, discarded_batch = parse_audit_result(
                    batch, result, stage="full"
                )

                kept.extend(kept_batch)
                discarded.extend(discarded_batch)

            except Exception as e:
                logger.error(
                    f"[audit:stage2] Batch {batch_idx} failed: {e}", exc_info=True
                )
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

        response = await self.client.completion(
            messages,
            json_format=True,
        )
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
        # Build raw items as dict for context manager.
        items_for_audit: list[dict] = []
        for item in batch:
            items_for_audit.append(
                {
                    "id": item["id"],
                    "title": item.get("title", "")[:200],
                    "summary": item.get("summary", "")[:800],
                    "source": item.get("source", ""),
                    "published_at": item.get("published_at", ""),
                    "content": item.get("content", ""),
                }
            )

        dimensions_context = self._format_dimensions(focus_dimensions)

        # Use global config + context manager to control prompt size.
        config = get_config()
        context_cfg = config.context
        # Default output tokens for full audit; can be made configurable later.
        max_output_tokens = 3000

        per_task_limits: dict = {
            "full_audit": {
                "max_input_ratio": 0.6,
                "max_chars_per_item": 1800,
            }
        }

        ctx_budget = ContextBudget(
            max_context_tokens=context_cfg.max_tokens,
            max_output_tokens=max_output_tokens,
            safety_ratio=context_cfg.compress_threshold,
            task_name="full_audit",
            per_task_limits=per_task_limits,
        )

        ctx_budget.add_block(
            ContextBlock.fixed("system", FULL_AUDIT_PROMPT, priority=10)
        )
        ctx_budget.add_block(ContextBlock.fixed("focus", focus, priority=9))
        ctx_budget.add_block(
            ContextBlock.fixed("dimensions", dimensions_context, priority=8)
        )
        ctx_budget.add_block(
            ContextBlock.variable(
                name="materials",
                payload=items_for_audit,
                strategy_name="structured_paragraphs",
                priority=5,
                per_item_key="content",
                max_chars_per_item=per_task_limits["full_audit"]["max_chars_per_item"],
            )
        )

        ctx_budget.compact()
        compact_items = ctx_budget.get_block_payload("materials")
        items_json = json.dumps(
            compact_items, ensure_ascii=False, separators=(",", ":")
        )

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
Return audit results in JSON format. Keep each audit_report brief (see Length Constraints in system prompt).
"""

        messages = [
            Message.system(FULL_AUDIT_PROMPT),
            Message.user(user_prompt),
        ]

        response = await self.client.completion(
            messages,
            max_tokens=max_output_tokens,
            json_format=True,
        )
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
        formatted: list[dict] = []
        for item in items:
            item_dict: dict = {
                "id": item["id"],
                "title": item.get("title", "")[:200],
                "summary": item.get("summary", "")[:800],
                "source": item.get("source", ""),
                "published_at": item.get("published_at", ""),
            }

            if include_content and item.get("content"):
                item_dict["content"] = item.get("content", "")

            formatted.append(item_dict)

        return json.dumps(formatted, ensure_ascii=False, separators=(",", ":"))

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
            if hasattr(dim, "name"):
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
