"""Compatibility shim for LLM message/tool models.

Canonical definitions live in distill_lib.core.models.llm.
"""

from distill_lib.core.models.llm import (
    CompletionResponse,
    Enum,
    FunctionDefinition,
    Literal,
    Message,
    MessageRole,
    ModelProvider,
    Optional,
    Tool,
    ToolCall,
    ToolChoice,
    Union,
    dataclass,
    enum_factory,
    field,
    time,
)

__all__ = [
    "CompletionResponse",
    "Enum",
    "FunctionDefinition",
    "Literal",
    "Message",
    "MessageRole",
    "ModelProvider",
    "Optional",
    "Tool",
    "ToolCall",
    "ToolChoice",
    "Union",
    "dataclass",
    "enum_factory",
    "field",
    "time",
]
