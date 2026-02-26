"""Compatibility shim for config loader helpers.

Canonical implementation lives in distill_lib.core.config.loader.
"""

from distill_lib.core.config.loader import (
    AgentLimitsConfig,
    ConfigPaths,
    ConfigValidationError,
    ContextConfig,
    EmbeddingConfig,
    GlobalConfig,
    ModelConfig,
    RateLimitConfig,
    get_api_key_env_var,
    get_api_key_for_provider,
    get_base_url_for_provider,
    get_config,
    get_config_path,
    get_model_config,
    is_api_key_configured,
    load_config,
    reload_config,
    validate_config,
)

__all__ = [
    "AgentLimitsConfig",
    "ConfigPaths",
    "ConfigValidationError",
    "ContextConfig",
    "EmbeddingConfig",
    "GlobalConfig",
    "ModelConfig",
    "RateLimitConfig",
    "get_api_key_env_var",
    "get_api_key_for_provider",
    "get_base_url_for_provider",
    "get_config",
    "get_config_path",
    "get_model_config",
    "is_api_key_configured",
    "load_config",
    "reload_config",
    "validate_config",
]
