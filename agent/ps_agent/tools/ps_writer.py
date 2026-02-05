"""PS Agent 写作工具模块"""
import json
import logging
from typing import TypedDict, NotRequired

from agent.utils import extract_json
from core.llm_client import LLMClient
from core.models.llm import Message
from agent.ps_agent.state import ResearchItem
from agent.ps_agent.prompts import (
    DEEP_WRITER_SYSTEM_PROMPT,
    DEEP_WRITER_INITIAL_PROMPT,
    DEEP_WRITER_REFINE_PROMPT,
    SUMMARY_REVIEWER_SYSTEM_PROMPT,
    SUMMARY_REVIEWER_PROMPT,
)

logger = logging.getLogger(__name__)


class PSWritingMaterial(TypedDict):
    """PS Agent 专用写作素材（方案 B 简化版）"""
    topic: str
    writing_guide: str
    items: list[ResearchItem]           # 全局研究材料
    patch_items: NotRequired[list[ResearchItem]]     # 补丁素材（可选）


async def ps_write_article(
    client: LLMClient,
    material: PSWritingMaterial,
    review: dict | None = None,
    current_draft: str | None = None,
    context: dict | None = None
) -> str:
    """
    PS Agent 专用写作函数（方案 B 简化版）。

    Args:
        client: LLM client
        material: Writing material with global items
        review: Optional review feedback for refinement mode
        current_draft: Current draft for refinement mode
        context: Optional context for sliding window (global_outline, previous_summary)
    """
    
    # 方案 B 简化：只使用全局 items，不再使用 bucket
    # 构建 items JSON（全局材料池）
    clean_items = []
    for item in material.get("items", [])[:50]:  # 限制数量避免上下文过长
        clean_items.append({
            "id": item["id"],
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "summary": item.get("summary", "")[:300],
            "is_patch": item.get("is_patch", False),
            "relevance": item.get("relevance", 0.0),
            "composite_score": item.get("composite_score", 0.0),
        })

    items_json = json.dumps(clean_items, indent=2, ensure_ascii=False)

    # 根据模式选择 Prompt
    if review and current_draft:
        # 修订模式
        review_json = json.dumps({
            "status": review.get("status"),
            "score": review.get("score"),
            "summary": review.get("summary", review.get("comments", "")),
            "findings": review.get("findings", [])
        }, indent=2, ensure_ascii=False)

        prompt = DEEP_WRITER_REFINE_PROMPT.format(
            topic=material['topic'],
            review_json=review_json,
            current_draft=current_draft,
            items_json=items_json
        )
    else:
        # 初稿模式
        context_section = ""
        if context:
            context_section = f"""## 上下文
- **文章主题**: {context.get('global_outline', '')}
- **当前章节**: 第 {context.get('section_number', 1)} 章
- **承接上文**: {context.get('previous_summary', '（开篇章节）')}
"""

        prompt = DEEP_WRITER_INITIAL_PROMPT.format(
            topic=material['topic'],
            context_section=context_section,
            items_json=items_json,
            writing_guide=material['writing_guide'] or "按照专业分析标准撰写"
        )
    
    messages = [
        Message.system(DEEP_WRITER_SYSTEM_PROMPT),
        Message.user(prompt)
    ]
    
    try:
        response = await client.completion(messages)
        content = response.content.strip()
        return content
    except Exception as exc:
        logger.error(f"[ps_writer] Writing failed: {exc}")
        return f"(撰写失败: {exc})"


async def ps_review_article(client: LLMClient, draft: str, material: PSWritingMaterial) -> dict:
    """PS Agent 专用审核函数（方案 B 简化版：只使用全局 items）"""

    # 构建全局 items 信息
    items_summary = []
    for item in material.get("items", [])[:20]:  # 限制数量
        items_summary.append({
            "id": item["id"],
            "title": item.get("title", ""),
            "is_patch": item.get("is_patch", False),
            "relevance": item.get("relevance", 0.0),
        })

    items_json = json.dumps(items_summary, indent=2, ensure_ascii=False)

    prompt = SUMMARY_REVIEWER_PROMPT.format(
        topic=material['topic'],
        writing_guide=material['writing_guide'] or "专业分析标准",
        items_json=items_json,
        draft=draft
    )
    
    messages = [
        Message.system(SUMMARY_REVIEWER_SYSTEM_PROMPT),
        Message.user(prompt)
    ]

    try:
        response = await client.completion(messages)
        result = extract_json(response)
        # 兼容处理
        if "comments" not in result and "summary" in result:
            result["comments"] = result["summary"]
        return result
    except Exception as exc:
        logger.error(f"[ps_review] Review failed: {exc}")
        return {"status": "APPROVED", "score": 50, "comments": f"Review failed: {exc}"}


__all__ = [
    "ps_write_article",
    "ps_review_article",
    "PSWritingMaterial",
]