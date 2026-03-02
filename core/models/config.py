from dataclasses import dataclass, field
from typing import Optional

from core.models.llm import ModelProvider


@dataclass
class RateLimitConfig:
    """Rate limiting and retry configuration dataclass"""

    # Rate limiting settings
    requests_per_minute: float = 60.0
    burst_size: int = 10
    enable_rate_limit: bool = True

    # Retry settings
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    enable_retry: bool = True


@dataclass
class ContextConfig:
    """Context management configuration dataclass"""

    # Context window settings
    max_tokens: int = 128000
    compress_threshold: float = 0.8


@dataclass
class AgentLimitsConfig:
    """Agent loop limiting configuration dataclass"""

    # Research phase limits
    max_iterations: int = 5
    max_tool_calls: int = 30
    max_curations: int = 3

    # Review phase limits
    max_plan_reviews: int = 2

    # Writing phase limits
    max_refines: int = 2

    # Layer 1 control
    enable_hard_limits: bool = True


@dataclass
class EmbeddingConfig:
    """Embedding service configuration (model/base_url from config, API key from env)."""

    model: str = "text-embedding-3-small"
    provider: ModelProvider = ModelProvider.OTHER
    base_url: Optional[str] = None


@dataclass
class GlobalConfig:
    """Global configuration dataclass"""

    model: "ModelConfig"
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    context: ContextConfig = field(default_factory=ContextConfig)
    agent_limits: "AgentLimitsConfig" = field(default_factory=lambda: AgentLimitsConfig())  # type: ignore[misc]
    lightweight_model: Optional["ModelConfig"] = None
    embedding: Optional[EmbeddingConfig] = None


@dataclass
class ModelConfig:
    """Model configuration dataclass"""

    model: str
    provider: ModelProvider
    base_url: Optional[str] = None  # Only required for OTHER provider
