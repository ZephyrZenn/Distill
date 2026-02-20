"""Embedding service for generating text embeddings.

This module provides embedding generation using OpenAI-compatible APIs.
Embeddings are used for semantic search in the memory system.

Configuration:
- config.toml [embedding]: model, provider, base_url
- Environment: EMBEDDING_API_KEY (API key only; required when using embedding)

Example config.toml:
    [embedding]
    model = "text-embedding-3-small"
    provider = "other"
    base_url = "https://api.openai.com/v1"

Example env:
    export EMBEDDING_API_KEY=sk-...
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Optional

from openai import AsyncOpenAI

from core.config.loader import get_config

logger = logging.getLogger(__name__)

# Default embedding dimensions for common models
EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

# Default embedding model
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_DIMENSION = 1536

# Context length limits for embedding models (tokens)
# Conservative estimate: ~4 chars per token for Chinese/English mixed content
EMBEDDING_MAX_CHARS = 6000  # Safe limit for 8192 token models
EMBEDDING_BATCH_SIZE = 20  # Max texts per batch to avoid total token overflow


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""

    pass


class EmbeddingNotConfiguredError(Exception):
    """Raised when embedding service is not properly configured."""

    def __init__(self, message: str = "Embedding service not configured"):
        super().__init__(message)


class EmbeddingService(ABC):
    """Abstract base class for embedding services."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Return the dimension of embeddings produced by this service."""
        raise NotImplementedError

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        raise NotImplementedError

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        raise NotImplementedError


class OpenAIEmbeddingService(EmbeddingService):
    """Embedding service using OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        base_url: Optional[str] = None,
        model: str = DEFAULT_EMBEDDING_MODEL,
    ):
        self.model = model
        self._dimension = EMBEDDING_DIMENSIONS.get(model, DEFAULT_EMBEDDING_DIMENSION)
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        if not text or not text.strip():
            raise EmbeddingError("Cannot embed empty text")

        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text,
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}", exc_info=True)
            raise EmbeddingError(f"Failed to generate embedding: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts with batching and truncation."""
        if not texts:
            return []

        # Truncate texts to safe length and track valid indices
        valid_texts = []
        valid_indices = []
        for i, text in enumerate(texts):
            if text and text.strip():
                # Truncate to safe length to avoid context overflow
                truncated = text[:EMBEDDING_MAX_CHARS]
                valid_texts.append(truncated)
                valid_indices.append(i)

        if not valid_texts:
            raise EmbeddingError("All texts are empty")

        # Process in batches to avoid total token overflow
        all_embeddings: list[list[float]] = []
        batch_start = 0

        while batch_start < len(valid_texts):
            batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(valid_texts))
            batch_texts = valid_texts[batch_start:batch_end]

            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch_texts,
                )
                batch_embeddings = [data.embedding for data in response.data]
                all_embeddings.extend(batch_embeddings)

                logger.debug(
                    "Embedded batch %d-%d/%d (batch_size=%d)",
                    batch_start,
                    batch_end,
                    len(valid_texts),
                    len(batch_texts),
                )
            except Exception as e:
                logger.error(
                    "Error generating batch embeddings (batch %d-%d): %s",
                    batch_start,
                    batch_end,
                    e,
                    exc_info=True,
                )
                raise EmbeddingError(f"Failed to generate batch embeddings: {e}") from e

            batch_start = batch_end

        # Re-map to original indices
        result = [None] * len(texts)
        for idx, embedding in zip(valid_indices, all_embeddings):
            result[idx] = embedding

        # Fill in None values with zero vectors (for empty strings)
        zero_vector = [0.0] * self._dimension
        for i in range(len(result)):
            if result[i] is None:
                result[i] = zero_vector

        return result


# Singleton instance
_embedding_service: Optional[EmbeddingService] = None


def get_embedding_model() -> str:
    """Get the embedding model name from config or use default.

    Prefers config.toml [embedding].model when present.
    Fallback: DEFAULT_EMBEDDING_MODEL
    """
    try:
        cfg = get_config()
        if cfg.embedding and cfg.embedding.model:
            return cfg.embedding.model
    except Exception:
        pass
    return DEFAULT_EMBEDDING_MODEL


def get_embedding_dimension() -> int:
    """Get the embedding dimension for the current model."""
    model = get_embedding_model()
    return EMBEDDING_DIMENSIONS.get(model, DEFAULT_EMBEDDING_DIMENSION)


def build_embedding_service() -> EmbeddingService:
    """Build an embedding service based on current configuration.

    API key: from EMBEDDING_API_KEY (env).
    Model and base_url: from config.toml [embedding] when present.

    Returns:
        An EmbeddingService instance.

    Raises:
        EmbeddingNotConfiguredError: If no valid API key is found.
    """
    api_key = os.getenv("EMBEDDING_API_KEY")
    if not api_key or not api_key.strip():
        raise EmbeddingNotConfiguredError(
            "No API key found for embedding service. Set EMBEDDING_API_KEY."
        )

    base_url = None
    try:
        cfg = get_config()
        if cfg.embedding:
            base_url = cfg.embedding.base_url
    except Exception:
        pass

    model = get_embedding_model()
    logger.info(
        "Building embedding service: model=%s, base_url=%s",
        model,
        base_url or "default",
    )
    return OpenAIEmbeddingService(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def get_embedding_service() -> EmbeddingService:
    """Get the singleton embedding service instance.

    Returns:
        The EmbeddingService instance.

    Raises:
        EmbeddingNotConfiguredError: If service cannot be initialized.
    """
    global _embedding_service

    if _embedding_service is None:
        _embedding_service = build_embedding_service()

    return _embedding_service


def is_embedding_configured() -> bool:
    """Check if embedding service can be configured.

    Requires EMBEDDING_API_KEY (env). Either config.toml [embedding]
    """
    api_key = os.getenv("EMBEDDING_API_KEY")
    if not api_key or not api_key.strip():
        return False
    try:
        cfg = get_config()
        if cfg.embedding:
            return True
    except Exception:
        return False
    return False


async def embed_text(text: str) -> list[float]:
    """Convenience function to embed a single text.

    Args:
        text: The text to embed.

    Returns:
        The embedding vector.
    """
    service = get_embedding_service()
    return await service.embed(text)


async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Convenience function to embed multiple texts.

    Args:
        texts: List of texts to embed.

    Returns:
        List of embedding vectors.
    """
    service = get_embedding_service()
    return await service.embed_batch(texts)
