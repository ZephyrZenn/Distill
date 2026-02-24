from typing import Optional

from agent.tools import is_search_engine_available
from core.config.loader import get_config, reload_config
from core.config.utils import write_config
from core.models.config import EmbeddingConfig, ModelConfig

from apps.backend.models.converters import (
    agent_limits_config_to_vo,
    apply_agent_limits_request,
    apply_context_request,
    apply_rate_limit_request,
    context_config_to_vo,
    embedding_config_to_vo,
    model_config_to_vo,
    rate_limit_config_to_vo,
    request_to_embedding_config,
    request_to_model_config,
)
from apps.backend.models.request import (
    AgentLimitsSettingRequest,
    ContextSettingRequest,
    EmbeddingSettingRequest,
    ModelConfigRequest,
    RateLimitSettingRequest,
)
from apps.backend.models.view_model import SettingVO


def get_setting() -> SettingVO:
    """Get current settings as a VO (model, lightweight_model, embedding, advanced)."""
    config = get_config()
    return SettingVO(
        model=model_config_to_vo(config.model),
        lightweight_model=(
            model_config_to_vo(config.lightweight_model)
            if config.lightweight_model else None
        ),
        embedding=embedding_config_to_vo(config.embedding),
        tavily_configured=is_search_engine_available(),
        rate_limit=rate_limit_config_to_vo(config.rate_limit),
        context=context_config_to_vo(config.context),
        agent_limits=agent_limits_config_to_vo(config.agent_limits),
    )


def update_setting(
    model: Optional[ModelConfig] = None,
    lightweight_model: Optional[ModelConfigRequest] = None,
    embedding: Optional[EmbeddingSettingRequest] = None,
    rate_limit: Optional[RateLimitSettingRequest] = None,
    context: Optional[ContextSettingRequest] = None,
    agent_limits: Optional[AgentLimitsSettingRequest] = None,
) -> None:
    """Update settings. Any section can be provided optionally."""
    cfg = get_config()
    if model is not None:
        cfg.model = model
    if lightweight_model is not None:
        cfg.lightweight_model = request_to_model_config(lightweight_model)
    if embedding is not None:
        cfg.embedding = request_to_embedding_config(embedding)
    apply_rate_limit_request(cfg.rate_limit, rate_limit)
    apply_context_request(cfg.context, context)
    apply_agent_limits_request(cfg.agent_limits, agent_limits)
    write_config(cfg)
    reload_config()