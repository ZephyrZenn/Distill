"""Compatibility shim for LLM client module.

Canonical implementation lives in distill_lib.core.llm_client.
"""

from distill_lib.core.llm_client import (
    APIKeyNotConfiguredError,
    CompletionResponse,
    GeminiClient,
    LLMClient,
    Message,
    ModelProvider,
    OpenAIClient,
    Tool,
    ToolCall,
    ToolChoice,
    auto_build_client,
    build_client,
)

__all__ = [
    "APIKeyNotConfiguredError",
    "CompletionResponse",
    "GeminiClient",
    "LLMClient",
    "Message",
    "ModelProvider",
    "OpenAIClient",
    "Tool",
    "ToolCall",
    "ToolChoice",
    "auto_build_client",
    "build_client",
]
