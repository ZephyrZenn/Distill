"""Bucket confidence threshold configuration.

This is the single source of truth for all bucket confidence thresholds
and scoring weights across the system. All prompts and code should reference these values.
"""

# Threshold values for bucket confidence matching
# Adjusted for deep analysis: lower threshold allows inclusion of longer research reports
BUCKET_THRESHOLDS = {
    "high": 0.35,  # Lowered from 0.40 to accommodate in-depth research reports
    "medium": 0.30,
    "low": 0.20,
}

# Threshold descriptions for prompts
THRESHOLD_DESCRIPTIONS = {
    "high": "0.35",
    "medium": "0.30",
    "low": "0.20",
}


def get_bucket_threshold(precision: str) -> float:
    """Get the threshold for a given precision level.

    Args:
        precision: One of "high", "medium", "low"

    Returns:
        The threshold value (0.0-1.0)
    """
    return BUCKET_THRESHOLDS.get(precision.lower(), 0.30)


def get_thresholds_for_prompt() -> str:
    """Get formatted threshold descriptions for use in prompts.

    Returns:
        Formatted string for prompt documentation
    """
    return f"""- **high**: {THRESHOLD_DESCRIPTIONS['high']}
- **medium**: {THRESHOLD_DESCRIPTIONS['medium']}
- **low**: {THRESHOLD_DESCRIPTIONS['low']}"""


__all__ = ["get_bucket_threshold", "get_thresholds_for_prompt", "BUCKET_THRESHOLDS"]


# 注意：方案 B 不再使用 bucket-specific scoring weights
# 相关功能已移至 material_curation.py 中的统一权重
# BUCKET_SCORING_WEIGHTS 和 DEFAULT_SCORING_WEIGHTS 已删除
