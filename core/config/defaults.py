from __future__ import annotations

"""
Centralized default configuration values.

Currently used to provide a single source of truth for Agent limits so that
PS Agent, config loader, and backend settings stay in sync.
"""

from core.models.config import AgentLimitsConfig

# Default agent loop limits used across the system when no explicit overrides
# are provided in config.toml or runtime state.
DEFAULT_AGENT_LIMITS = AgentLimitsConfig()

