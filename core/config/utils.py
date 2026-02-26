"""Compatibility shim for config utilities.

Canonical implementation lives in distill_lib.core.config.utils.
"""

from distill_lib.core.config.utils import (
    Any,
    Dict,
    GlobalConfig,
    asdict,
    create_default_config,
    enum_factory,
    get_config_summary,
    logger,
    logging,
    os,
    toml,
    validate_config_file_exists,
    write_config,
)

__all__ = [
    "Any",
    "Dict",
    "GlobalConfig",
    "asdict",
    "create_default_config",
    "enum_factory",
    "get_config_summary",
    "logger",
    "logging",
    "os",
    "toml",
    "validate_config_file_exists",
    "write_config",
]
