"""Compatibility wrapper for shared rate limiting utilities.

Canonical implementation now lives in distill_lib.rate_limiter.
"""

from distill_lib.rate_limiter import (  # noqa: F401
    RATE_LIMIT_PATTERNS,
    RateLimiter,
    RetryConfig,
    configure_rate_limiter,
    configure_retry,
    get_default_rate_limiter,
    get_default_retry_config,
    is_retryable_error,
    retry_with_backoff,
    with_rate_limit_and_retry,
)

__all__ = [
    "RATE_LIMIT_PATTERNS",
    "RateLimiter",
    "RetryConfig",
    "configure_rate_limiter",
    "configure_retry",
    "get_default_rate_limiter",
    "get_default_retry_config",
    "is_retryable_error",
    "retry_with_backoff",
    "with_rate_limit_and_retry",
]
