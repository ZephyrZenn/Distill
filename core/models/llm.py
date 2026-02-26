"""Compatibility shim for LLM message/tool models.

Canonical definitions live in distill_lib.core.models.llm.
"""

from distill_lib.core.models.llm import (
    CompletionResponse,
    FunctionDefinition,
    Message,
    MessageRole,
    ModelProvider,
    Tool,
    ToolCall,
    ToolChoice,
    enum_factory,
)

__all__ = [
    "CompletionResponse",
    "FunctionDefinition",
    "Message",
    "MessageRole",
    "ModelProvider",
    "Tool",
    "ToolCall",
    "ToolChoice",
    "enum_factory",
]
