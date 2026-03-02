import logging
import os
from dataclasses import dataclass
from typing import Optional

import toml

from core.models.config import (
    AgentLimitsConfig,
    ContextConfig,
    EmbeddingConfig,
    GlobalConfig,
    ModelConfig,
    RateLimitConfig,
)
from core.config.defaults import DEFAULT_AGENT_LIMITS
from core.models.llm import ModelProvider

from .utils import (
    create_default_config,
    get_config_summary,
    validate_config_file_exists,
)

logger = logging.getLogger(__name__)

_config: Optional[GlobalConfig] = None


class ConfigValidationError(Exception):
    """Raised when configuration validation fails"""

    pass


@dataclass
class ConfigPaths:
    """Configuration file paths for different environments"""

    dev: str = "config.toml"
    prod: str = "/app/config.toml"
    test: str = "config.toml"


def get_config_path() -> str:
    """Get the appropriate config file path based on environment"""
    env = os.getenv("ENV", "dev").lower()
    paths = ConfigPaths()

    if env == "prod":
        return paths.prod
    elif env == "test":
        return paths.test
    else:
        return paths.dev


def _validate_model_config(config: dict) -> None:
    """Validate model configuration required fields."""
    required = ["model", "provider"]
    for field in required:
        value = config.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            raise ConfigValidationError(f"Missing required field: model.{field}")

    provider = config["provider"]
    valid_providers = [p.value for p in ModelProvider]
    if provider not in valid_providers:
        raise ConfigValidationError(
            f"Invalid provider: {provider}. Must be one of: {valid_providers}"
        )

    # Validate base_url is required for OTHER provider
    if provider == ModelProvider.OTHER.value:
        base_url = config.get("base_url")
        if not base_url or (isinstance(base_url, str) and not base_url.strip()):
            raise ConfigValidationError("base_url is required when provider is 'other'")


def get_api_key_env_var(provider: ModelProvider) -> str:
    """Get the environment variable name for a provider's API key.

    Environment variable mapping:
    - OPENAI: OPENAI_API_KEY
    - DEEPSEEK: DEEPSEEK_API_KEY
    - GEMINI: GEMINI_API_KEY
    - OTHER: MODEL_API_KEY
    """
    env_var_map = {
        ModelProvider.OPENAI: "OPENAI_API_KEY",
        ModelProvider.DEEPSEEK: "DEEPSEEK_API_KEY",
        ModelProvider.GEMINI: "GEMINI_API_KEY",
        ModelProvider.OTHER: "MODEL_API_KEY",
    }
    return env_var_map.get(provider, "MODEL_API_KEY")


def get_api_key_for_provider(provider: ModelProvider) -> Optional[str]:
    """Get the API key for a given provider from environment variables.

    Returns None if not configured, allowing the system to start without API keys.
    """
    env_var = get_api_key_env_var(provider)
    api_key = os.getenv(env_var)

    if not api_key:
        logger.warning(
            f"API key not configured. Set {env_var} environment variable for provider '{provider.value}'"
        )
        return None

    return api_key


def is_api_key_configured(provider: Optional[ModelProvider] = None) -> bool:
    """Check if the API key is configured for the given or current provider.

    Args:
        provider: Optional provider to check. If None, uses current config provider.

    Returns:
        True if API key is configured, False otherwise.
    """
    if provider is None:
        try:
            config = get_config()
            provider = config.model.provider
        except Exception:
            return False

    env_var = get_api_key_env_var(provider)
    api_key = os.getenv(env_var)
    return bool(api_key and api_key.strip())


def get_base_url_for_provider(
    provider: ModelProvider, config_base_url: Optional[str] = None
) -> Optional[str]:
    """Get the base URL for a given provider.

    Auto-determined URLs:
    - OPENAI: https://api.openai.com/v1
    - DEEPSEEK: https://api.deepseek.com
    - GEMINI: None (uses Google SDK)
    - OTHER: Must be provided in config
    """
    base_url_map = {
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com",
        ModelProvider.GEMINI: None,
        ModelProvider.OTHER: config_base_url,
    }

    return base_url_map.get(provider)


def _to_model_config(config: dict) -> ModelConfig:
    """Convert dict configuration to ModelConfig dataclass."""
    provider = ModelProvider(config["provider"])
    config_base_url = config.get("base_url")

    # Get auto-determined base_url (or use config for OTHER)
    base_url = get_base_url_for_provider(provider, config_base_url)

    return ModelConfig(
        model=config["model"].strip(),
        provider=provider,
        base_url=base_url,
    )


def _to_rate_limit_config(config: dict) -> RateLimitConfig:
    """Convert dict configuration to RateLimitConfig dataclass.

    All fields are optional and will use defaults if not provided.
    """
    return RateLimitConfig(
        # Rate limiting settings
        requests_per_minute=float(config.get("requests_per_minute", 60.0)),
        burst_size=int(config.get("burst_size", 10)),
        enable_rate_limit=config.get("enable_rate_limit", True),
        # Retry settings
        max_retries=int(config.get("max_retries", 3)),
        base_delay=float(config.get("base_delay", 1.0)),
        max_delay=float(config.get("max_delay", 60.0)),
        enable_retry=config.get("enable_retry", True),
    )


def _to_context_config(config: dict) -> ContextConfig:
    """Convert dict configuration to ContextConfig dataclass.

    All fields are optional and will use defaults if not provided.
    """
    return ContextConfig(
        max_tokens=int(config.get("max_tokens", 128000)),
        compress_threshold=float(config.get("compress_threshold", 0.8)),
    )


def _to_agent_limits_config(config: dict) -> AgentLimitsConfig:
    """Convert dict configuration to AgentLimitsConfig dataclass.

    All fields are optional and will use defaults if not provided.
    """
    return AgentLimitsConfig(
        # Research phase limits
        max_iterations=int(
            config.get("max_iterations", DEFAULT_AGENT_LIMITS.max_iterations)
        ),
        max_tool_calls=int(
            config.get("max_tool_calls", DEFAULT_AGENT_LIMITS.max_tool_calls)
        ),
        max_curations=int(
            config.get("max_curations", DEFAULT_AGENT_LIMITS.max_curations)
        ),
        # Review phase limits
        max_plan_reviews=int(
            config.get("max_plan_reviews", DEFAULT_AGENT_LIMITS.max_plan_reviews)
        ),
        # Writing phase limits
        max_refines=int(
            config.get("max_refines", DEFAULT_AGENT_LIMITS.max_refines)
        ),
        # Layer 1 control
        enable_hard_limits=config.get(
            "enable_hard_limits", DEFAULT_AGENT_LIMITS.enable_hard_limits
        ),
    )


def _to_embedding_config(config: dict) -> EmbeddingConfig:
    """Convert [embedding] section to EmbeddingConfig. All fields optional."""
    provider_str = config.get("provider", "other")
    try:
        provider = ModelProvider(provider_str)
    except ValueError:
        provider = ModelProvider.OTHER
    return EmbeddingConfig(
        model=str(config.get("model", "text-embedding-3-small")).strip(),
        provider=provider,
        base_url=config.get("base_url") and str(config.get("base_url")).strip() or None,
    )


def load_config(
    reload: bool = False, path: Optional[str] = None
) -> GlobalConfig:
    """Load configuration with caching and validation"""
    global _config

    if _config and not reload:
        return _config

    if not path:
        config_path = get_config_path()
    else:
        config_path = path

    if not os.path.exists(config_path):
        try:
            default_config = create_default_config()
            directory = os.path.dirname(config_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                toml.dump(default_config, f)
            logger.info("Created default configuration at %s", config_path)
        except Exception as e:
            raise ConfigValidationError(
                f"Failed to create default configuration at {config_path}: {e}"
            )

    if not validate_config_file_exists(config_path):
        raise ConfigValidationError(f"Configuration file not found: {config_path}")

    try:
        # Load file configuration
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = toml.load(f)

        # NOTE: 禁止使用环境变量覆盖 config.toml 的配置。

        summary = get_config_summary(file_config)
        logger.info(f"Configuration summary: {summary}")

    except toml.TomlDecodeError as e:
        raise ConfigValidationError(f"Invalid TOML configuration: {e}")
    except Exception as e:
        raise ConfigValidationError(f"Error reading configuration file: {e}")

    # Validate and build global config
    model_config = file_config.get("model", {})
    _validate_model_config(model_config)

    # Parse rate limit config (optional, uses defaults if not present)
    rate_limit_config = file_config.get("rate_limit", {})
    rate_limit_cfg = _to_rate_limit_config(rate_limit_config)

    # Parse context config (optional, uses defaults if not present)
    context_config = file_config.get("context", {})
    context_cfg = _to_context_config(context_config)

    # Parse agent limits config (optional, uses defaults if not present)
    agent_limits_config = file_config.get("agent_limits", {})
    agent_limits_cfg = _to_agent_limits_config(agent_limits_config)

    # Optional: lightweight model (e.g. for audit/batch tasks)
    lightweight_cfg = None
    lightweight_config = file_config.get("lightweight_model", {})
    if (
        lightweight_config
        and lightweight_config.get("model")
        and lightweight_config.get("provider")
    ):
        _validate_model_config(lightweight_config)
        lightweight_cfg = _to_model_config(lightweight_config)

    # Optional: embedding (model/base_url from config, API key from env)
    embedding_cfg = None
    embedding_config = file_config.get("embedding", {})
    if embedding_config:
        embedding_cfg = _to_embedding_config(embedding_config)

    global_cfg = GlobalConfig(
        model=_to_model_config(model_config),
        rate_limit=rate_limit_cfg,
        context=context_cfg,
        agent_limits=agent_limits_cfg,
        lightweight_model=lightweight_cfg,
        embedding=embedding_cfg,
    )

    _config = global_cfg
    logger.info(
        "Configuration loaded successfully. Model: %s (%s)",
        global_cfg.model.model,
        global_cfg.model.provider.value,
    )

    return _config


def get_config() -> GlobalConfig:
    """Get the current configuration, loading it if necessary"""
    return load_config()


def reload_config() -> GlobalConfig:
    """Force reload the configuration"""
    return load_config(reload=True)


def get_model_config(model_name: Optional[str] = None) -> ModelConfig:
    """Get the configured model. Additional models are not supported."""
    config = get_config()
    default_model_name = config.model.model
    if model_name and model_name not in {"default", default_model_name}:
        raise ConfigValidationError(
            f"Model '{model_name}' not found. Only the default model is configured."
        )

    return config.model


def validate_config() -> bool:
    """Validate the current configuration without loading it"""
    try:
        load_config(reload=True)
        return True
    except ConfigValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error during configuration validation: {e}")
        return False
