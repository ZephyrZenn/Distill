import asyncio
import json
import logging
import random
import re
from abc import ABC, abstractmethod
from typing import Optional, Union

from google import genai
from google.genai import types
from openai import AsyncOpenAI

from core.config.loader import get_api_key_for_provider, get_config, get_api_key_env_var
from core.models.feed import FeedArticle
from core.models.llm import (
    CompletionResponse,
    Message,
    ModelProvider,
    Tool,
    ToolCall,
    ToolChoice,
)
from core.rate_limiter import (
    RateLimiter,
    RetryConfig,
    get_default_rate_limiter,
    get_default_retry_config,
    is_retryable_error,
)

logger = logging.getLogger(__name__)

"""Brief client for summarizing articles using AI models.
This module provides an abstract base class for AI clients and concrete implementations"""

LOG_PREVIEW_CHARS = 360


def _preview_text(text: str | None, *, limit: int = LOG_PREVIEW_CHARS) -> str:
    if not text:
        return ""
    clean = str(text).replace("\n", " ").strip()
    if len(clean) <= limit:
        return clean
    return clean[:limit] + "..."


def _messages_summary(messages: list[Message]) -> str:
    parts: list[str] = []
    for msg in messages[-6:]:
        role = getattr(msg, "role", "unknown")
        parts.append(f"{role}:{len(getattr(msg, 'content', '') or '')}")
    return ",".join(parts)


class APIKeyNotConfiguredError(Exception):
    """Raised when API key is not configured for the current provider."""

    def __init__(self, provider: ModelProvider):
        self.provider = provider
        self.env_var = get_api_key_env_var(provider)
        super().__init__(
            f"API key not configured. Please set {self.env_var} environment variable for provider '{provider.value}'"
        )


class LLMClient(ABC):
    def __init__(
        self,
        api_key: str,
        base_url: Optional[str],
        model: str,
        rate_limiter: Optional[RateLimiter] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_rate_limit: bool = True,
        enable_retry: bool = True,
    ):
        """
        Initialize the AIClient with a prompt and limit.
        Args:
            api_key (str): The API key for the AI service.
            base_url (str): The base URL for the AI service.
            model (str): The model to use for summarization.
            rate_limiter (RateLimiter): Rate limiter instance for controlling request rate.
            retry_config (RetryConfig): Retry configuration for handling transient errors.
            enable_rate_limit (bool): Whether to enable rate limiting (default: True).
            enable_retry (bool): Whether to enable retry on errors (default: True).
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

        # Rate limiting and retry configuration
        self.rate_limiter = (
            rate_limiter
            if rate_limiter
            else (get_default_rate_limiter() if enable_rate_limit else None)
        )
        self.retry_config = (
            retry_config
            if retry_config
            else (get_default_retry_config() if enable_retry else None)
        )

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting if configured."""
        if self.rate_limiter:
            await self.rate_limiter.acquire()

    async def _execute_with_retry(self, func, *args, **kwargs):
        """Execute a function with retry logic if configured.

        This method ensures rate limiting is applied before each retry attempt,
        not just the first attempt.
        """
        if not self.retry_config:
            return await func(*args, **kwargs)

        # 自定义重试逻辑，在每次重试前重新应用速率限制
        last_exception = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # 每次尝试前都应用速率限制（包括第一次）
                await self._apply_rate_limit()
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e

                # 检查是否是可重试的错误
                if not is_retryable_error(e):
                    logger.warning("Non-retryable error in %s: %s", func.__name__, e)
                    raise

                # 如果配置了特定的异常类型，检查是否匹配
                if (
                    self.retry_config.retryable_exceptions
                    and self.retry_config.retryable_exceptions != (Exception,)
                ):
                    if not isinstance(e, self.retry_config.retryable_exceptions):
                        logger.warning(
                            "Error type %s not in retryable_exceptions, not retrying",
                            type(e).__name__,
                        )
                        raise

                if attempt == self.retry_config.max_retries:
                    logger.error(
                        "Max retries (%d) exceeded in %s: %s",
                        self.retry_config.max_retries,
                        func.__name__,
                        e,
                    )
                    raise

                # 计算延迟
                delay = min(
                    self.retry_config.base_delay
                    * (self.retry_config.exponential_base**attempt),
                    self.retry_config.max_delay,
                )

                # 添加抖动
                if self.retry_config.jitter:
                    delay *= 0.5 + random.random()

                logger.warning(
                    "Retry %d/%d after %.2fs in %s due to: %s",
                    attempt + 1,
                    self.retry_config.max_retries,
                    delay,
                    func.__name__,
                    e,
                )
                await asyncio.sleep(delay)

        # 如果所有重试都失败，抛出最后一个异常
        if last_exception:
            raise last_exception
        raise RuntimeError(f"Retry loop completed without result in {func.__name__}")

    @abstractmethod
    async def completion(self, prompt, **kwargs) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def completion_with_tools(
        self,
        messages: Union[list[Message], list[dict]],
        tools: Union[list[Tool], list[dict]] | None = None,
        tool_choice: ToolChoice = "auto",
        **kwargs,
    ) -> Union[CompletionResponse, dict]:
        """支持 function calling 的 completion 方法

        支持两种调用方式：
        1. 使用类型安全的类对象（推荐）
        2. 使用字典格式（向后兼容）

        Args:
            messages: 消息列表（Message 对象列表或字典列表）
            tools: 工具定义列表（Tool 对象列表或字典列表）
            tool_choice: 工具选择策略，"auto" | "none" | {"type": "function", "function": {"name": "..."}}
            **kwargs: 其他参数

        Returns:
            CompletionResponse 对象（如果输入是类对象）或字典（如果输入是字典）
        """
        raise NotImplementedError()


class GeminiClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        model: str,
        rate_limiter: Optional[RateLimiter] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_rate_limit: bool = True,
        enable_retry: bool = True,
    ):
        super().__init__(
            api_key=api_key,
            base_url=None,
            model=model,
            rate_limiter=rate_limiter,
            retry_config=retry_config,
            enable_rate_limit=enable_rate_limit,
            enable_retry=enable_retry,
        )
        # 创建客户端实例，避免每次调用都创建
        self.client = genai.Client(
            api_key=self.api_key,
            http_options=types.HttpOptions(api_version="v1alpha"),
        )

    async def completion(self, prompt, **kwargs) -> str:
        try:
            # Apply rate limiting
            await self._apply_rate_limit()

            async def _do_completion():
                resp = await self.client.aio.models.generate_content(
                    model=self.model, contents=prompt
                )
                logger.info(
                    "GeminiClient completion content_chars=%d preview=%s",
                    len(resp.text or ""),
                    _preview_text(resp.text),
                )
                return resp.text

            # Apply retry
            return await self._execute_with_retry(_do_completion)
        except Exception as e:
            logger.error(f"Error in GeminiClient: {e}", exc_info=True)
            raise e

    async def completion_with_tools(
        self,
        messages: Union[list[Message], list[dict]],
        tools: Union[list[Tool], list[dict]] | None = None,
        tool_choice: ToolChoice = "auto",
        **kwargs,
    ) -> Union[CompletionResponse, dict]:
        """支持 function calling 的 completion 方法（Gemini 格式）"""
        # 检测输入类型并转换
        use_dict = (
            isinstance(messages, list) and messages and isinstance(messages[0], dict)
        )

        if use_dict:
            # 字典格式：转换为类对象，调用后再转换回字典
            msg_objects = [Message.from_dict(msg) for msg in messages]  # type: ignore
            tool_objects = [Tool.from_dict(tool) for tool in tools] if tools else None  # type: ignore
        else:
            # 类对象格式
            msg_objects = messages  # type: ignore
            tool_objects = tools  # type: ignore

        # Apply rate limiting first
        await self._apply_rate_limit()

        async def _do_completion_with_tools():
            return await self._gemini_completion_with_tools_impl(
                msg_objects, tool_objects, tool_choice, **kwargs
            )

        try:
            response = await self._execute_with_retry(_do_completion_with_tools)
            # 如果输入是字典，返回字典格式
            if use_dict:
                return response.to_dict()
            return response
        except Exception as e:
            logger.error(
                f"Error in GeminiClient.completion_with_tools: {e}", exc_info=True
            )
            raise e

    async def _gemini_completion_with_tools_impl(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        tool_choice: ToolChoice = "auto",  # noqa: ARG002
        **kwargs,
    ) -> CompletionResponse:
        """Internal implementation for completion_with_tools."""
        try:
            # 转换 messages 格式为 Gemini 格式
            gemini_contents = []
            for msg in messages:
                if msg.role == "system":
                    # Gemini 使用 system_instruction 处理 system 消息
                    # 这里我们将其作为第一个 user 消息的一部分
                    if gemini_contents:
                        existing_text = ""
                        if gemini_contents[0].get("parts"):
                            existing_text = gemini_contents[0]["parts"][0].get(
                                "text", ""
                            )
                        gemini_contents[0] = {
                            "role": "user",
                            "parts": [
                                {"text": f"System: {msg.content}\n\n{existing_text}"}
                            ],
                        }
                    else:
                        gemini_contents.append(
                            {
                                "role": "user",
                                "parts": [{"text": f"System: {msg.content}"}],
                            }
                        )
                elif msg.role == "user":
                    gemini_contents.append(
                        {"role": "user", "parts": [{"text": msg.content}]}
                    )
                elif msg.role == "assistant":
                    gemini_contents.append(
                        {"role": "model", "parts": [{"text": msg.content}]}
                    )
                elif msg.role == "tool":
                    # Gemini 使用 function_response 格式
                    tool_name = msg.name or ""
                    tool_content = msg.content
                    gemini_contents.append(
                        {
                            "role": "function",
                            "parts": [
                                {
                                    "function_response": {
                                        "name": tool_name,
                                        "response": tool_content,
                                    }
                                }
                            ],
                        }
                    )

            # 转换 tools 格式为 Gemini 格式
            gemini_tools = None
            if tools:
                gemini_tools = []
                for tool in tools:
                    if tool.type == "function":
                        gemini_tools.append(
                            {
                                "function_declarations": [
                                    {
                                        "name": tool.function.name,
                                        "description": tool.function.description,
                                        "parameters": tool.function.parameters,
                                    }
                                ]
                            }
                        )

            # 构建请求
            request_params = {
                "model": self.model,
                "contents": gemini_contents,
            }

            if gemini_tools:
                request_params["tools"] = gemini_tools

            # 添加其他 kwargs
            request_params.update(kwargs)

            resp = await self.client.aio.models.generate_content(**request_params)

            # 解析响应
            content = resp.text if hasattr(resp, "text") and resp.text else None
            tool_calls = []

            # 检查是否有 function_calls
            if hasattr(resp, "candidates") and resp.candidates:
                candidate = resp.candidates[0]
                if hasattr(candidate, "content") and candidate.content:
                    if hasattr(candidate.content, "parts"):
                        for part in candidate.content.parts:
                            if hasattr(part, "function_call"):
                                fc = part.function_call
                                tool_calls.append(
                                    ToolCall(
                                        id=f"call_{len(tool_calls)}",  # Gemini 不提供 ID，我们生成一个
                                        name=fc.name if hasattr(fc, "name") else "",
                                        arguments=(
                                            json.dumps(fc.args)
                                            if hasattr(fc, "args")
                                            else "{}"
                                        ),
                                    )
                                )

            finish_reason = (
                getattr(resp.candidates[0], "finish_reason", None)
                if hasattr(resp, "candidates") and resp.candidates
                else None
            )
            logger.info(
                "GeminiClient tools finish=%s tools=%d content_chars=%d tool_calls=%d preview=%s",
                finish_reason,
                len(tools or []),
                len(content or ""),
                len(tool_calls),
                _preview_text(content),
            )

            return CompletionResponse(
                content=content,
                tool_calls=tool_calls if tool_calls else None,
                finish_reason=finish_reason,
            )
        except Exception as e:
            logger.error(
                f"Error in GeminiClient.completion_with_tools: {e}", exc_info=True
            )
            raise e


class OpenAIClient(LLMClient):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        rate_limiter: Optional[RateLimiter] = None,
        retry_config: Optional[RetryConfig] = None,
        enable_rate_limit: bool = True,
        enable_retry: bool = True,
    ):
        super().__init__(
            base_url=base_url,
            model=model,
            api_key=api_key,
            rate_limiter=rate_limiter,
            retry_config=retry_config,
            enable_rate_limit=enable_rate_limit,
            enable_retry=enable_retry,
        )
        # 创建异步客户端实例，避免每次调用都创建
        self.client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url)

    async def completion(self, prompt: Union[str, list[Message]], **kwargs) -> str:
        """Completion 方法，支持字符串或消息列表

        Args:
            prompt: 如果是字符串，将构造为 user message；如果是消息列表，直接使用
            **kwargs: 其他参数

        Returns:
            LLM 返回的文本内容
        """
        try:
            # Apply rate limiting
            await self._apply_rate_limit()

            # 处理输入参数：如果是字符串，转换为 Message 列表
            if isinstance(prompt, str):
                messages = [Message.user(prompt)]
            else:
                messages = prompt

            # 转换为字典格式
            messages_dict = [msg.to_dict() for msg in messages]

            async def _do_completion():
                resp = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages_dict,
                    stream=False,
                    max_tokens=8192,
                )
                content = resp.choices[0].message.content or ""
                logger.info(
                    "OpenAIClient completion finish=%s usage=%s content_chars=%d preview=%s",
                    resp.choices[0].finish_reason,
                    resp.usage,
                    len(content),
                    _preview_text(content),
                )
                return resp.choices[0].message.content

            # Apply retry
            return await self._execute_with_retry(_do_completion)
        except Exception as e:
            logger.error(f"Error in OpenAIClient: {e}", exc_info=True)
            raise e

    async def completion_with_tools(
        self,
        messages: Union[list[Message], list[dict]],
        tools: Union[list[Tool], list[dict]] | None = None,
        tool_choice: ToolChoice = "auto",
        **kwargs,
    ) -> Union[CompletionResponse, dict]:
        """支持 function calling 的 completion 方法"""
        # 检测输入类型并转换
        use_dict = (
            isinstance(messages, list) and messages and isinstance(messages[0], dict)
        )

        if use_dict:
            # 字典格式：转换为类对象，调用后再转换回字典
            msg_objects = [Message.from_dict(msg) for msg in messages]  # type: ignore
            tool_objects = [Tool.from_dict(tool) for tool in tools] if tools else None  # type: ignore
        else:
            # 类对象格式
            msg_objects = messages  # type: ignore
            tool_objects = tools  # type: ignore

        # Apply rate limiting first
        await self._apply_rate_limit()

        async def _do_completion_with_tools():
            return await self._openai_completion_with_tools_impl(
                msg_objects, tool_objects, tool_choice, **kwargs
            )

        try:
            response = await self._execute_with_retry(_do_completion_with_tools)
            # 如果输入是字典，返回字典格式
            if use_dict:
                return response.to_dict()
            return response
        except Exception as e:
            logger.error(
                f"Error in OpenAIClient.completion_with_tools: {e}", exc_info=True
            )
            raise e

    async def _openai_completion_with_tools_impl(
        self,
        messages: list[Message],
        tools: list[Tool] | None = None,
        tool_choice: ToolChoice = "auto",
        **kwargs,
    ) -> CompletionResponse:
        """Internal implementation for completion_with_tools."""
        # 转换 tool_choice 格式
        tool_choice_param = None
        if tool_choice == "none":
            tool_choice_param = "none"
        elif tool_choice == "auto":
            tool_choice_param = "auto"
        elif isinstance(tool_choice, dict):
            tool_choice_param = tool_choice

        # 转换 messages 为字典格式
        messages_dict = [msg.to_dict() for msg in messages]

        # 准备请求参数
        request_params = {
            "model": self.model,
            "messages": messages_dict,
            "stream": False,
        }

        # 如果有工具，添加 tools 和 tool_choice 参数
        if tools:
            request_params["tools"] = [tool.to_dict() for tool in tools]
            if tool_choice_param is not None:
                request_params["tool_choice"] = tool_choice_param

        # 添加其他 kwargs
        request_params.update(kwargs)

        resp = await self.client.chat.completions.create(**request_params)

        message = resp.choices[0].message

        # 提取工具调用
        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    )
                )

        logger.info(
            "OpenAIClient tools finish=%s tools=%d content_chars=%d tool_calls=%d preview=%s",
            resp.choices[0].finish_reason,
            len(tools or []),
            len(message.content or ""),
            len(tool_calls),
            _preview_text(message.content),
        )

        return CompletionResponse(
            content=message.content,
            tool_calls=tool_calls if tool_calls else None,
            finish_reason=resp.choices[0].finish_reason,
        )


def build_client() -> LLMClient:
    """Build an AI client based on current configuration.

    Raises:
        APIKeyNotConfiguredError: If the API key is not set for the current provider.
    """
    config = get_config()
    model_cfg = config.model
    rate_limit_cfg = config.rate_limit

    # Get API key from environment variable based on provider
    api_key = get_api_key_for_provider(model_cfg.provider)

    if not api_key:
        raise APIKeyNotConfiguredError(model_cfg.provider)

    # Create rate limiter and retry config based on configuration
    rate_limiter = None
    retry_config = None

    if rate_limit_cfg.enable_rate_limit:
        rate_limiter = RateLimiter(
            requests_per_minute=rate_limit_cfg.requests_per_minute,
            burst_size=rate_limit_cfg.burst_size,
        )

    if rate_limit_cfg.enable_retry:
        retry_config = RetryConfig(
            max_retries=rate_limit_cfg.max_retries,
            base_delay=rate_limit_cfg.base_delay,
            max_delay=rate_limit_cfg.max_delay,
        )

    return _build_client(
        client_type=model_cfg.provider,
        api_key=api_key,
        base_url=model_cfg.base_url,
        model=model_cfg.model,
        rate_limiter=rate_limiter,
        retry_config=retry_config,
        enable_rate_limit=rate_limit_cfg.enable_rate_limit,
        enable_retry=rate_limit_cfg.enable_retry,
    )


def _build_client(
    client_type: ModelProvider,
    api_key: str,
    base_url: Optional[str],
    model: str,
    rate_limiter: Optional[RateLimiter] = None,
    retry_config: Optional[RetryConfig] = None,
    enable_rate_limit: bool = True,
    enable_retry: bool = True,
) -> LLMClient:
    """
    Build an AI client based on the model type.
    Args:
        client_type (ModelProvider): The type of client to create
        api_key (str): The API key for the AI service.
        base_url (str): The base URL for the AI service.
        model (str): The model to use for summarization.
        rate_limiter (RateLimiter): Rate limiter instance for controlling request rate.
        retry_config (RetryConfig): Retry configuration for handling transient errors.
        enable_rate_limit (bool): Whether to enable rate limiting.
        enable_retry (bool): Whether to enable retry on errors.
    Returns:
        AIClient: An instance of the appropriate AIClient subclass.
    """
    if client_type == ModelProvider.GEMINI:
        return GeminiClient(
            api_key=api_key,
            model=model,
            rate_limiter=rate_limiter,
            retry_config=retry_config,
            enable_rate_limit=enable_rate_limit,
            enable_retry=enable_retry,
        )
    elif client_type in (
        ModelProvider.OPENAI,
        ModelProvider.DEEPSEEK,
        ModelProvider.OTHER,
    ):
        # All OpenAI-compatible providers use OpenAIClient
        return OpenAIClient(
            base_url=base_url,
            model=model,
            api_key=api_key,
            rate_limiter=rate_limiter,
            retry_config=retry_config,
            enable_rate_limit=enable_rate_limit,
            enable_retry=enable_retry,
        )
    else:
        raise ValueError(f"Unsupported client type: {client_type}")
