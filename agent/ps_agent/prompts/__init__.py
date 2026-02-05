"""PS Agent Prompts - 统一导出所有阶段的 Prompt"""

# Bootstrap 阶段
from .bootstrap import (
    BOOTSTRAP_SYSTEM_PROMPT,
    BOOTSTRAP_INTENT_DIMENSIONS_PROMPT,
    BOOTSTRAP_EXCLUSION_PROMPT,
    BOOTSTRAP_REPLAN_PROMPT,
    build_bootstrap_user_prompt,
)

# Research Planning 阶段
from .research import (
    RESEARCH_PLANNER_PROMPT,
    RESEARCH_PLANNER_PATCH_PROMPT,
)

# Evaluation 阶段
from .evaluation import (
    PLAN_REVIEW_PROMPT,
)

# Structure 阶段
from .structure import (
    STRUCTURE_SYSTEM_PROMPT,
    STRUCTURE_USER_PROMPT,
)

# Writing 阶段
from .writing import (
    DEEP_WRITER_SYSTEM_PROMPT,
    DEEP_WRITER_INITIAL_PROMPT,
    DEEP_WRITER_REFINE_PROMPT,
)

# Review 阶段
from .review import (
    SUMMARY_REVIEWER_SYSTEM_PROMPT,
    SUMMARY_REVIEWER_PROMPT,
)

# Audit 阶段 (P0: Two-stage LLM audit)
from .snippet_audit import SNIPPET_AUDIT_PROMPT
from .full_audit import FULL_AUDIT_PROMPT

# Spiral Collection (P1)
from .audit_analysis import AUDIT_ANALYSIS_PROMPT

# 向后兼容别名
WRITER_SYSTEM_PROMPT = DEEP_WRITER_SYSTEM_PROMPT


__all__ = [
    # Bootstrap
    "BOOTSTRAP_SYSTEM_PROMPT",
    "BOOTSTRAP_INTENT_DIMENSIONS_PROMPT",
    "BOOTSTRAP_EXCLUSION_PROMPT",
    "BOOTSTRAP_REPLAN_PROMPT",
    "build_bootstrap_user_prompt",
    # Research Planning
    "RESEARCH_PLANNER_PROMPT",
    "RESEARCH_PLANNER_PATCH_PROMPT",
    # Evaluation
    "PLAN_REVIEW_PROMPT",
    # Structure
    "STRUCTURE_SYSTEM_PROMPT",
    "STRUCTURE_USER_PROMPT",
    # Writing
    "WRITER_SYSTEM_PROMPT",  # 兼容别名
    "DEEP_WRITER_SYSTEM_PROMPT",
    "DEEP_WRITER_INITIAL_PROMPT",
    "DEEP_WRITER_REFINE_PROMPT",
    # Review
    "SUMMARY_REVIEWER_SYSTEM_PROMPT",
    "SUMMARY_REVIEWER_PROMPT",
    # Audit (P0: Two-stage LLM audit)
    "SNIPPET_AUDIT_PROMPT",
    "FULL_AUDIT_PROMPT",
    # Spiral Collection (P1)
    "AUDIT_ANALYSIS_PROMPT",
]
