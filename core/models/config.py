"""Compatibility shim for config models.

Canonical definitions live in distill_lib.core.models.config.
"""

from distill_lib.core.models.config import (
    AgentLimitsConfig,
    ContextConfig,
    EmbeddingConfig,
    GlobalConfig,
    ModelConfig,
    ModelProvider,
    Optional,
    RateLimitConfig,
    dataclass,
    field,
)

__all__ = [
    "AgentLimitsConfig",
    "ContextConfig",
    "EmbeddingConfig",
    "GlobalConfig",
    "ModelConfig",
    "ModelProvider",
    "Optional",
    "RateLimitConfig",
    "dataclass",
    "field",
]
