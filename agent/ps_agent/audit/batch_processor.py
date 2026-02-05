"""Batch processing logic for LLM audit."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Handles batching of items for LLM audit.

    Args:
        batch_size: Number of items per batch (default: 15)
    """

    def __init__(self, batch_size: int = 15) -> None:
        self.batch_size = batch_size

    def create_batches[T](self, items: Sequence[T]) -> list[list[T]]:
        """Split items into batches.

        Args:
            items: Sequence of research items

        Returns:
            List of batches (each batch is a list of items)
        """
        batches = []
        for i in range(0, len(items), self.batch_size):
            batch = list(items[i : i + self.batch_size])
            batches.append(batch)

        logger.info(
            f"[BatchProcessor] Created {len(batches)} batches "
            f"(batch_size={self.batch_size}, total_items={len(items)})"
        )
        return batches

    def estimate_tokens(
        self, batch: Sequence[dict], include_content: bool = False
    ) -> int:
        """Estimate token count for a batch.

        Rough estimation: 1 char ≈ 0.3-0.4 tokens (for English mixed with Chinese)

        Args:
            batch: List of research items (dict-like with title/summary/content)
            include_content: Whether to include content length in estimation

        Returns:
            Estimated token count
        """
        total_chars = 0

        for item in batch:
            title = len(item.get("title", ""))
            summary = len(item.get("summary", ""))
            content = len(item.get("content", "")) if include_content else 0

            # JSON overhead (quotes, braces, commas)
            total_chars += title + summary + content + 200

        # Character to token ratio (conservative estimate)
        # Chinese uses more tokens per character, English uses fewer
        estimated_tokens = int(total_chars * 0.4)

        logger.debug(
            f"[BatchProcessor] Estimated tokens: {estimated_tokens} "
            f"(batch_size={len(batch)}, include_content={include_content})"
        )
        return estimated_tokens


__all__ = ["BatchProcessor"]
