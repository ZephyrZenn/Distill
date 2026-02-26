"""Converters between core dataclasses and API Pydantic models."""

import os

from distill_lib.core.config.loader import (
    get_base_url_for_provider,
    is_api_key_configured,
    get_api_key_env_var,
)
from distill_lib.core.models.config import (
    AgentLimitsConfig,
    ContextConfig,
    EmbeddingConfig,
    ModelConfig,
    RateLimitConfig,
)
from distill_lib.core.models.llm import ModelProvider

from .request import (
    AgentLimitsSettingRequest,
    ContextSettingRequest,
    EmbeddingSettingRequest,
    ModelConfigRequest,
    RateLimitSettingRequest,
)
from .view_model import (
    AgentLimitsSettingVO,
    ContextSettingVO,
    EmbeddingSettingVO,
    ModelSettingVO,
    RateLimitSettingVO,
)


def model_config_to_vo(config: ModelConfig) -> ModelSettingVO:
    """Convert core ModelConfig dataclass to API response VO.

    Args:
        config: The core ModelConfig dataclass

    Returns:
        ModelSettingVO for API response

    Note: API keys are managed via environment variables, not exposed in API.
    """
    return ModelSettingVO(
        model=config.model,
        provider=config.provider.value,
        base_url=config.base_url if config.provider == ModelProvider.OTHER else None,
        api_key_configured=is_api_key_configured(config.provider),
        api_key_env_var=get_api_key_env_var(config.provider),
    )


def embedding_config_to_vo(c: EmbeddingConfig | None) -> EmbeddingSettingVO | None:
    if c is None:
        return None
    api_key = os.getenv("EMBEDDING_API_KEY")
    return EmbeddingSettingVO(
        model=c.model,
        provider=c.provider.value,
        base_url=c.base_url if c.provider == ModelProvider.OTHER else None,
        api_key_configured=bool(api_key and api_key.strip()),
        api_key_env_var="EMBEDDING_API_KEY",
    )


def request_to_embedding_config(request: EmbeddingSettingRequest) -> EmbeddingConfig:
    provider = ModelProvider(request.provider)
    base_url = get_base_url_for_provider(provider, request.base_url)
    return EmbeddingConfig(
        model=request.model,
        provider=provider,
        base_url=base_url,
    )


def request_to_model_config(request: ModelConfigRequest) -> ModelConfig:
    """Convert API request to core ModelConfig dataclass.

    Args:
        request: The ModelConfigRequest from API

    Returns:
        ModelConfig dataclass for business logic

    Note: Base URL is auto-determined except for 'other' provider.
    """
    provider = ModelProvider(request.provider)
    base_url = get_base_url_for_provider(provider, request.base_url)

    return ModelConfig(
        model=request.model,
        provider=provider,
        base_url=base_url,
    )


def rate_limit_config_to_vo(c: RateLimitConfig) -> RateLimitSettingVO:
    return RateLimitSettingVO(
        requests_per_minute=c.requests_per_minute,
        burst_size=c.burst_size,
        enable_rate_limit=c.enable_rate_limit,
        max_retries=c.max_retries,
        base_delay=c.base_delay,
        max_delay=c.max_delay,
        enable_retry=c.enable_retry,
    )


def context_config_to_vo(c: ContextConfig) -> ContextSettingVO:
    return ContextSettingVO(
        max_tokens=c.max_tokens,
        compress_threshold=c.compress_threshold,
    )


def agent_limits_config_to_vo(c: AgentLimitsConfig) -> AgentLimitsSettingVO:
    return AgentLimitsSettingVO(
        max_iterations=c.max_iterations,
        max_tool_calls=c.max_tool_calls,
        max_curations=c.max_curations,
        max_plan_reviews=c.max_plan_reviews,
        max_refines=c.max_refines,
        enable_hard_limits=c.enable_hard_limits,
    )


def _apply_request_to_dataclass(current, request_obj, field_names: list[str]):
    """Update dataclass instance with non-None fields from request (Pydantic model or dict)."""
    if request_obj is None:
        return
    d = (
        request_obj
        if isinstance(request_obj, dict)
        else request_obj.model_dump(exclude_none=True)
    )
    for key in field_names:
        if key in d:
            setattr(current, key, d[key])


def apply_rate_limit_request(
    cfg: RateLimitConfig, req: RateLimitSettingRequest | None
) -> None:
    _apply_request_to_dataclass(
        cfg,
        req,
        [
            "requests_per_minute",
            "burst_size",
            "enable_rate_limit",
            "max_retries",
            "base_delay",
            "max_delay",
            "enable_retry",
        ],
    )


def apply_context_request(
    cfg: ContextConfig, req: ContextSettingRequest | None
) -> None:
    _apply_request_to_dataclass(cfg, req, ["max_tokens", "compress_threshold"])


def apply_agent_limits_request(
    cfg: AgentLimitsConfig, req: AgentLimitsSettingRequest | None
) -> None:
    _apply_request_to_dataclass(
        cfg,
        req,
        [
            "max_iterations",
            "max_tool_calls",
            "max_curations",
            "max_plan_reviews",
            "max_refines",
            "enable_hard_limits",
        ],
    )
