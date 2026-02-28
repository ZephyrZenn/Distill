"""Tool schemas and execution helpers for the agentic LangGraph workflow.

This module does three jobs:
1. Define tool *schemas* for model-side function calling.
2. Execute tool calls coming back from the model.
3. Normalize and deduplicate research items so later stages are stable.
"""

from __future__ import annotations

import json
import logging
import time

from agent.utils import extract_json
from agent.ps_agent.state import PSAgentState
from core.models.llm import Message, Tool, ToolCall

from .handlers import (
    handle_search_feeds,
    handle_search_memory,
    handle_search_web,
)
from .normalize import (
    merge_items,
    normalize_feed_articles,
    normalize_memories,
    normalize_web_results,
)
from .payload import json_default, truncate_for_tool_message
from .schemas import RegisteredTool, build_tool_schemas

logger = logging.getLogger(__name__)


def _parse_arguments(arguments: str) -> dict:
    if not arguments:
        return {}
    try:
        return json.loads(arguments, strict=False)
    except json.JSONDecodeError:
        return extract_json(arguments)


def _tool_registry(current_date: str) -> dict[str, RegisteredTool]:
    schemas = build_tool_schemas(current_date=current_date)
    schema_by_name = {tool.function.name: tool for tool in schemas}

    return {
        "search_feeds": RegisteredTool(
            schema=schema_by_name["search_feeds"], handler=handle_search_feeds
        ),
        "search_web": RegisteredTool(
            schema=schema_by_name["search_web"], handler=handle_search_web
        ),
        "search_memory": RegisteredTool(
            schema=schema_by_name["search_memory"], handler=handle_search_memory
        ),
    }


def get_registered_tools(*, current_date: str) -> list[Tool]:
    """Public helper: model-facing tool schemas."""
    registry = _tool_registry(current_date)
    return [entry.schema for entry in registry.values()]


def get_researcher_tools(*, current_date: str) -> list[Tool]:
    """Get tools for the researcher node (search_feeds and search_web only).

    The researcher only needs to plan searches, not execute fetch_content or
    search_memory. finish_research is signaled by returning no tool calls.
    """
    registry = _tool_registry(current_date)
    return [
        registry["search_feeds"].schema,
        registry["search_web"].schema,
        registry["search_memory"].schema,
    ]


async def execute_tool_calls(state: PSAgentState, tool_calls: list[ToolCall]) -> dict:
    """Execute tool calls and return state updates.

    This function is intentionally "thick" so the rest of the graph stays simple.
    """
    if not tool_calls:
        return {}

    run_id = state.get("run_id", "-")

    def _emit(message: str) -> None:
        callback = state.get("on_step")
        if callback:
            try:
                callback(message)
            except Exception:
                pass

    registry = _tool_registry(state["current_date"])

    messages: list[Message] = []
    research_items = list(state.get("research_items", []))
    query_history = list(state.get("query_history", []) or [])

    for call in tool_calls:
        entry = registry.get(call.name)
        if not entry:
            logger.warning("未知工具: %s", call.name)
            tool_payload = {"error": f"unknown tool: {call.name}"}
            messages.append(
                Message.tool(
                    content=json.dumps(tool_payload, ensure_ascii=False),
                    name=call.name,
                    tool_call_id=call.id,
                )
            )
            continue

        args = _parse_arguments(call.arguments)

        if state.get("execution_mode") == "PATCH_MODE" and call.name in (
            "search_feeds",
            "search_web",
        ):
            args["is_patch"] = True

        _emit(f"🔧 tool: {call.name} args={json.dumps(args, ensure_ascii=False)[:240]}")
        logger.info(
            "[tool] run_id=%s name=%s call_id=%s args=%s",
            run_id,
            call.name,
            call.id,
            json.dumps(args, ensure_ascii=False)[:800],
        )
        try:
            payload = await entry.handler(args, state)
        except Exception as exc:
            logger.exception("工具执行失败: %s", call.name)
            payload = {"error": str(exc), "tool": call.name, "args": args}

        meta = payload.get("meta") if isinstance(payload, dict) else None
        try:
            payload_chars = len(
                json.dumps(payload, ensure_ascii=False, default=json_default)
            )
        except Exception:
            payload_chars = -1
        logger.info(
            "[tool] run_id=%s name=%s ok=%s payload_chars=%d meta=%s",
            run_id,
            call.name,
            "error" not in payload,
            payload_chars,
            json.dumps(meta, ensure_ascii=False)[:400] if meta is not None else "",
        )
        if isinstance(meta, dict):
            _emit(
                f"🔧 tool: {call.name} meta={json.dumps(meta, ensure_ascii=False)[:240]}"
            )

        messages.append(
            Message.tool(
                content=truncate_for_tool_message(payload),
                name=call.name,
                tool_call_id=call.id,
            )
        )

        if call.name == "search_feeds":
            articles = payload.get("articles", []) or []
            new_items = normalize_feed_articles(articles)
            research_items = merge_items(research_items, new_items)
        elif call.name == "search_web":
            query_text = str(args.get("query", "") or "")
            results = payload.get("results", []) or []

            if query_text:
                if not query_history or query_history[-1].get("query") != query_text:
                    query_history.append(
                        {
                            "query": query_text,
                            "timestamp": time.time(),
                            "results_count": len(results),
                        }
                    )
                    if len(query_history) > 50:
                        query_history = query_history[-50:]
                    logger.info(
                        f"[tool] Recorded query to history: '{query_text[:50]}...' "
                        f"results={len(results)}"
                    )
            new_items = normalize_web_results(
                results, is_patch=bool(args.get("is_patch", False))
            )
            research_items = merge_items(research_items, new_items)
        elif call.name == "search_memory":
            memories = payload.get("memories", []) or []
            new_items = normalize_memories(memories)
            research_items = merge_items(research_items, new_items)

        logger.info(
            "[tool] run_id=%s after=%s research_items=%d",
            run_id,
            call.name,
            len(research_items),
        )
        _emit(f"🔧 tool: after {call.name} research_items={len(research_items)}")

    return {
        "messages": messages,
        "research_items": research_items,
        "query_history": query_history,
        "tool_call_count": state.get("tool_call_count", 0) + len(tool_calls),
        "status": "researching",
        "last_error": None,
    }


__all__ = [
    "execute_tool_calls",
    "get_registered_tools",
    "get_researcher_tools",
]
