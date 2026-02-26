"""Tool schemas and types for the agentic LangGraph workflow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from distill_lib.core.models.llm import FunctionDefinition, Tool

from agent.ps_agent.state import PSAgentState

# Keep tool message payloads bounded so the conversation does not explode.
TOOL_MESSAGE_MAX_CHARS = 10_000
MATCH_TEXT_MAX_CHARS = 800
MIN_MATCH_SCORE = 0.18

# When a tool payload is too large, we shrink it (instead of truncating raw JSON)
# so the model still gets stable structure + meta (query/count/etc).
WEB_RESULT_SNIPPET_MAX_CHARS = 450
# 放宽 feed / 写作阶段的内容截断，避免证据过早被丢弃
FEED_SUMMARY_MAX_CHARS = 1_200
TOOL_MAX_LIST_ITEMS = 12

ToolHandler = Callable[[dict, PSAgentState], Coroutine[Any, Any, dict]]


@dataclass(frozen=True)
class RegisteredTool:
    """A tool entry with both schema and executor."""

    schema: Tool
    handler: ToolHandler


def build_tool_schemas(*, current_date: str) -> list[Tool]:
    """Build model-facing tool definitions.

    We thread `current_date` into descriptions to strongly bias toward "today".
    """
    recency_hint = (
        f"今天是 {current_date}。除非明确需要背景信息，请优先检索 24 小时内的内容。"
    )

    return [
        Tool(
            function=FunctionDefinition(
                name="search_feeds",
                description=(
                    "从系统内的 RSS 订阅源检索相关文章。"
                    "返回标题、链接、摘要、发布时间等元信息。"
                    f"{recency_hint}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "检索关键词，可为空表示广泛扫描。支持 -关键词 排除语法（如 'OpenAI -百度'）",
                        },
                        "hour_gap": {
                            "type": "integer",
                            "description": "时间窗口（小时），建议 24 或更小。",
                            "default": 24,
                            "minimum": 1,
                            "maximum": 168,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回的最大文章数量。",
                            "default": 30,
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "exclude_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "排除包含这些关键词的文章。",
                        },
                    },
                    "required": [],
                    "additionalProperties": False,
                },
            )
        ),
        Tool(
            function=FunctionDefinition(
                name="search_web",
                description=(
                    "在互联网上搜索最新信息，返回搜索结果的摘要/片段（而非全文）。"
                    "适合用于补充订阅源未覆盖的实时信息。若需要正文，请再调用 fetch_content。"
                    f"{recency_hint}"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "具体、可执行的搜索查询语句。",
                        },
                        "time_range": {
                            "type": "string",
                            "enum": ["day", "week", "month", "year"],
                            "description": '时间范围限制。做"当日重点"时应优先 day。',
                            "default": "day",
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "希望返回的最大结果数。",
                            "default": 8,
                            "minimum": 1,
                            "maximum": 20,
                        },
                        "topic": {
                            "type": "string",
                            "enum": ["news", "finance"],
                            "description": (
                                "搜索类别："
                                "'news' 用于实时新闻（政治、体育、重大时事）；"
                                "'finance' 用于金融相关；"
                            ),
                            "default": "news",
                        },
                        "exclude_keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "排除包含这些关键词的结果。",
                        },
                    },
                    "required": ["query"],
                    "additionalProperties": False,
                },
            )
        ),
        Tool(
            function=FunctionDefinition(
                name="search_memory",
                description=(
                    "搜索历史记忆中的背景材料与趋势上下文。"
                    "用于补充解释性背景，而不是替代当日信息。"
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "keywords": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "关键词列表，建议 2-6 个。",
                        },
                        "days_ago": {
                            "type": "integer",
                            "description": "回溯天数，默认 14 天。",
                            "default": 14,
                            "minimum": 1,
                            "maximum": 365,
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回结果数量上限。",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 50,
                        },
                    },
                    "required": ["keywords"],
                    "additionalProperties": False,
                },
            )
        )
    ]
