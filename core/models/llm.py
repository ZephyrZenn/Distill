from datetime import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional, Union


class ModelProvider(Enum):
    """Enum for model providers."""

    GEMINI = "gemini"
    OPENAI = "openai"
    DEEPSEEK = "deepseek"
    OTHER = "other"


def enum_factory(items):
    result = {}
    for key, value in items:
        if isinstance(value, Enum):
            result[key] = value.value
        elif isinstance(value, time):
            result[key] = value.strftime("%H:%M")
        else:
            result[key] = value
    return result


# Type definitions for messages and tools
MessageRole = Literal["user", "assistant", "system", "tool"]
ToolChoice = Union[Literal["auto", "none"], dict]


@dataclass
class ToolCall:
    """表示工具调用

    Attributes:
        id: 工具调用ID
        name: 函数名称
        arguments: 函数参数（JSON字符串）
        type: 工具调用类型（OpenAI 兼容格式）
    """
    id: str
    name: str
    arguments: str
    type: str = "function"

    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "id": self.id,
            "type": self.type,
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ToolCall":
        """从字典创建"""
        func = data.get("function", {})
        return cls(
            id=data.get("id", ""),
            name=func.get("name", ""),
            arguments=func.get("arguments", "{}"),
            type=data.get("type", "function"),
        )


@dataclass
class Message:
    """表示消息
    
    Attributes:
        role: 消息角色 (user, assistant, system, tool)
        content: 消息内容
        name: 工具名称（仅当 role 为 tool 时使用）
        tool_call_id: 工具调用ID（仅当 role 为 tool 时使用）
        tool_calls: 工具调用列表（仅当 role 为 assistant 时使用）
        priority: 消息优先级（0=最高，1=高，2=中，3=低），默认3
    """
    role: MessageRole
    content: str
    name: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    priority: int = 3  # 默认优先级为3（低）
    
    def to_dict(self) -> dict:
        """转换为字典格式（OpenAI格式）"""
        result = {
            "role": self.role,
            "content": self.content,
        }
        
        if self.role == "tool":
            if self.name:
                result["name"] = self.name
            if self.tool_call_id:
                result["tool_call_id"] = self.tool_call_id
        elif self.role == "assistant" and self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        
        # 注意：priority字段不包含在to_dict中，因为LLM API不需要它
        # priority只在内部使用，用于压缩逻辑
        
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        """从字典创建"""
        tool_calls = []
        if data.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in data["tool_calls"]]
        
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            name=data.get("name"),
            tool_call_id=data.get("tool_call_id"),
            tool_calls=tool_calls,
            priority=data.get("priority", 3),  # 默认优先级为3
        )
    
    @classmethod
    def user(cls, content: str) -> "Message":
        """创建用户消息"""
        return cls(role="user", content=content)
    
    @classmethod
    def assistant(cls, content: str, tool_calls: Optional[list[ToolCall]] = None) -> "Message":
        """创建助手消息"""
        return cls(role="assistant", content=content, tool_calls=tool_calls or [])
    
    @classmethod
    def system(cls, content: str) -> "Message":
        """创建系统消息"""
        return cls(role="system", content=content)
    
    @classmethod
    def tool(cls, content: str, name: str, tool_call_id: str) -> "Message":
        """创建工具响应消息"""
        return cls(role="tool", content=content, name=name, tool_call_id=tool_call_id)
    
    def is_protected(self) -> bool:
        """判断是否为受保护消息（priority=0，不允许被压缩）"""
        return self.priority == 0
    
    def set_priority(self, priority: int) -> "Message":
        """设置消息优先级（返回自身以支持链式调用）"""
        self.priority = priority
        return self


@dataclass
class FunctionDefinition:
    """函数定义
    
    Attributes:
        name: 函数名称
        description: 函数描述
        parameters: 参数Schema（JSON Schema格式）
    """
    name: str
    description: str
    parameters: dict
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FunctionDefinition":
        """从字典创建"""
        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            parameters=data.get("parameters", {}),
        )


@dataclass
class Tool:
    """表示工具定义（OpenAI function calling格式）
    
    Attributes:
        type: 工具类型，固定为 "function"
        function: 函数定义
    """
    function: FunctionDefinition
    type: str = "function"
    
    def to_dict(self) -> dict:
        """转换为字典格式（OpenAI格式）"""
        return {
            "type": self.type,
            "function": self.function.to_dict(),
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "Tool":
        """从字典创建"""
        return cls(
            type=data.get("type", "function"),
            function=FunctionDefinition.from_dict(data.get("function", {})),
        )


@dataclass
class CompletionResponse:
    """表示 completion_with_tools 的返回结果
    
    Attributes:
        content: LLM的文本响应
        tool_calls: 工具调用列表（如果有）
        finish_reason: 完成原因
    """
    content: Optional[str]
    tool_calls: Optional[list[ToolCall]] = None
    finish_reason: Optional[str] = None
    
    def to_dict(self) -> dict:
        """转换为字典格式"""
        result = {
            "content": self.content,
            "finish_reason": self.finish_reason,
        }
        if self.tool_calls:
            result["tool_calls"] = [tc.to_dict() for tc in self.tool_calls]
        else:
            result["tool_calls"] = None
        return result
    
    @classmethod
    def from_dict(cls, data: dict) -> "CompletionResponse":
        """从字典创建"""
        tool_calls = None
        if data.get("tool_calls"):
            tool_calls = [ToolCall.from_dict(tc) for tc in data["tool_calls"]]
        
        return cls(
            content=data.get("content"),
            tool_calls=tool_calls,
            finish_reason=data.get("finish_reason"),
        )
