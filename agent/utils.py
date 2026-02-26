"""Backward-compatible re-export for shared JSON helpers now in distill_lib.core."""

from distill_lib.core.utils import (
    AsyncOpenAI,
    cosine_similarity,
    extract_json,
    get_config,
    get_query_embedding,
    is_duplicate_query,
    json,
    logger,
    logging,
    np,
    os,
    re,
    set_embedding_model,
)

__all__ = [
    "AsyncOpenAI",
    "cosine_similarity",
    "extract_json",
    "get_config",
    "get_query_embedding",
    "is_duplicate_query",
    "json",
    "logger",
    "logging",
    "np",
    "os",
    "re",
    "set_embedding_model",
]
