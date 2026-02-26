"""Backward-compatible re-export for workflow writing tool now in distill_lib.agent."""

from distill_lib.agent.tools.writing_tool import (
    AgentCriticResult,
    CRITIC_SYSTEM_PROMPT_TEMPLATE,
    CRITIC_USER_PROMPT_TEMPLATE,
    LLMClient,
    Message,
    WRITER_DEEP_DIVE_SYSTEM_PROMPT_TEMPLATE,
    WRITER_DEEP_DIVE_USER_PROMPT_TEMPLATE,
    WRITER_FLASH_NEWS_PROMPT,
    WritingMaterial,
    extract_json,
    logger,
    logging,
    review_article,
    write_article,
)

__all__ = [
    "AgentCriticResult",
    "CRITIC_SYSTEM_PROMPT_TEMPLATE",
    "CRITIC_USER_PROMPT_TEMPLATE",
    "LLMClient",
    "Message",
    "WRITER_DEEP_DIVE_SYSTEM_PROMPT_TEMPLATE",
    "WRITER_DEEP_DIVE_USER_PROMPT_TEMPLATE",
    "WRITER_FLASH_NEWS_PROMPT",
    "WritingMaterial",
    "extract_json",
    "logger",
    "logging",
    "review_article",
    "write_article",
]
