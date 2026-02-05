import re
import json
import logging
import os

import numpy as np
from openai import AsyncOpenAI

from core.config.loader import get_config

logger = logging.getLogger(__name__)


def _clean_control_characters(text: str) -> str:
    """Remove or replace invalid control characters in JSON string.
    
    JSON spec only allows these control characters when escaped:
    - Newline, carriage return, tab are allowed in JSON structure (between values)
    - Inside string values, they must be escaped as \\n, \\r, \\t
    
    LLMs sometimes output raw control characters that break parsing.
    """
    # Replace common problematic control characters with their escaped versions
    # or remove them entirely
    result = []
    for char in text:
        code = ord(char)
        if code < 32:  # Control character range
            if char == '\n':
                result.append('\n')  # Keep newlines for JSON formatting
            elif char == '\r':
                result.append('')    # Remove carriage returns
            elif char == '\t':
                result.append(' ')   # Replace tabs with spaces
            else:
                result.append('')    # Remove other control characters
        else:
            result.append(char)
    return ''.join(result)


def  extract_json(text: str) -> dict:
    """
    Extract JSON from LLM response, handling:
    - Pure JSON text
    - Markdown code blocks (```json ... ``` or ``` ... ```)
    - Invalid control characters from LLM output
    - Extra whitespace and newlines
    """
    if not text:
        raise ValueError("Empty text provided")
    
    text = text.strip()

    # Try multiple patterns for markdown code blocks
    patterns = [
        r"```(?:json|JSON)?\s*\n([\s\S]*?)\n```",  # Standard code block
        r"```(?:json|JSON)?\s*([\s\S]*?)```",       # Code block without newlines
    ]
    
    json_str = None
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            json_str = match.group(1).strip()
            break
    
    if json_str is None:
        # Try to find JSON object directly (starts with { and ends with })
        brace_match = re.search(r'\{[\s\S]*\}', text)
        if brace_match:
            json_str = brace_match.group(0).strip()
        else:
            json_str = text

    # Clean control characters BEFORE parsing (this is the key fix)
    json_str = _clean_control_characters(json_str)
    
    # Try parsing with strict=False first (allows control chars in strings)
    try:
        return json.loads(json_str, strict=False)
    except json.JSONDecodeError as e:
        logger.warning(
            "First JSON parse attempt failed at position %d: %s",
            e.pos, e.msg
        )
    
    # Second attempt: replace fancy quotes with standard JSON quotes
    sanitized = (
        json_str.replace(""", '"')
        .replace(""", '"')
        .replace("'", "'")
        .replace("'", "'")
    )
    try:
        return json.loads(sanitized, strict=False)
    except json.JSONDecodeError as e:
        logger.warning(
            "Second JSON parse attempt (after sanitizing quotes) failed at position %d: %s",
            e.pos, e.msg
        )
    
    # If that fails, try additional cleanup
    # Remove any remaining problematic characters more aggressively
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', sanitized)
    
    try:
        return json.loads(cleaned, strict=False)
    except json.JSONDecodeError as e:
        logger.error(
            "JSON parse error at position %d: %s\nContext: %s",
            e.pos,
            e.msg,
            repr(cleaned[max(0, e.pos - 50):e.pos + 50])
        )
        raise ValueError(
            f"Failed to parse JSON. Error at position {e.pos}: {e.msg}\n"
            f"Near: {repr(cleaned[max(0, e.pos - 30):e.pos + 30])}"
        ) from e


# ============================================================================
# Embedding utilities for query deduplication (P1: Spiral Collection)
# ============================================================================

# Cache the client to avoid recreating it
_embedding_client: AsyncOpenAI | None = None
_embedding_model: str = "text-embedding-3-small"  # Cost-effective embedding model


def _get_embedding_client() -> AsyncOpenAI:
    """Get or create the embedding client."""
    global _embedding_client

    if _embedding_client is None:
        config = get_config()
        model_cfg = config.model

        # Use the same API key and base_url as the main LLM client
        api_key = os.getenv("OPENAI_API_KEY") or model_cfg.api_key
        base_url = model_cfg.base_url

        if not api_key:
            logger.warning("No API key found for embeddings, deduplication will be disabled")
            raise ValueError("No API key available for embeddings")

        _embedding_client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    return _embedding_client


def set_embedding_model(model: str) -> None:
    """Set the embedding model to use.

    Args:
        model: Model name (e.g., "text-embedding-3-small", "text-embedding-3-large")
    """
    global _embedding_model
    _embedding_model = model
    logger.info(f"Embedding model set to: {model}")


async def get_query_embedding(query: str) -> "np.ndarray | None":
    """Get embedding vector for a query string.

    Args:
        query: The query text to embed

    Returns:
        numpy array of shape (embedding_dim,) or None if failed
    """
    try:
        client = _get_embedding_client()
        response = await client.embeddings.create(
            model=_embedding_model,
            input=query,
        )
        embedding = response.data[0].embedding
        return np.array(embedding, dtype=np.float32)
    except Exception as e:
        logger.error(f"Failed to get embedding for query '{query[:50]}...': {e}")
        return None


def cosine_similarity(vec1: "np.ndarray", vec2: "np.ndarray") -> float:
    """Calculate cosine similarity between two vectors.

    Args:
        vec1: First embedding vector
        vec2: Second embedding vector

    Returns:
        Similarity score between 0.0 and 1.0
    """
    if vec1 is None or vec2 is None:
        return 0.0

    norm1 = np.linalg.norm(vec1)
    norm2 = np.linalg.norm(vec2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return float(np.dot(vec1, vec2) / (norm1 * norm2))


async def is_duplicate_query(
    new_query: str,
    query_history: list[dict],
    similarity_threshold: float = 0.85,
) -> bool:
    """Check if a query is semantically similar to any in history.

    Args:
        new_query: The new query to check
        query_history: List of previous queries with embeddings
            Format: [{"query": str, "timestamp": float, "results_count": int, "embedding": np.ndarray}, ...]
        similarity_threshold: Minimum similarity to consider as duplicate (default: 0.85)

    Returns:
        True if the query is a duplicate, False otherwise
    """
    if not query_history:
        return False

    try:
        new_embedding = await get_query_embedding(new_query)
        if new_embedding is None:
            # If embedding fails, assume it's not a duplicate
            return False

        for historical_query in query_history:
            # Skip if no embedding stored
            if "embedding" not in historical_query or historical_query["embedding"] is None:
                continue

            hist_embedding = historical_query["embedding"]

            # Calculate similarity
            similarity = cosine_similarity(new_embedding, hist_embedding)

            if similarity >= similarity_threshold:
                logger.info(
                    f"Duplicate query detected: similarity={similarity:.3f} "
                    f"new='{new_query[:50]}...' hist='{historical_query['query'][:50]}...'"
                )
                return True

        return False

    except Exception as e:
        logger.error(f"Error checking duplicate query: {e}", exc_info=True)
        return False
