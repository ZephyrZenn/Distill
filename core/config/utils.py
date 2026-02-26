"""Compatibility shim for config utilities.

Canonical implementation lives in distill_lib.core.config.utils.
"""

from distill_lib.core.config.utils import (
    create_default_config,
    get_config_summary,
    validate_config_file_exists,
    write_config,
)

__all__ = [
    "create_default_config",
    "get_config_summary",
    "validate_config_file_exists",
    "write_config",
]
