"""写作和审查工具函数模块

提供文章写作和审查相关的工具函数。
"""

import json
import logging

from agent.models import (
    WritingMaterial,
    AgentCriticResult,
)
from agent.prompts import (
    PRIMARY_BRIEF_SYSTEM_PROMPT,
    PRIMARY_BRIEF_USER_PROMPT,
    OPTIONAL_SECTION_SYSTEM_PROMPT,
    OPTIONAL_SECTION_USER_PROMPT,
    WRITER_FLASH_NEWS_PROMPT,
    WRITER_DEEP_DIVE_SYSTEM_PROMPT_TEMPLATE,
    WRITER_DEEP_DIVE_USER_PROMPT_TEMPLATE,
    CRITIC_SYSTEM_PROMPT_TEMPLATE,
    CRITIC_USER_PROMPT_TEMPLATE,
)
from agent.utils import extract_json
from core.llm_client import LLMClient
from core.models.llm import Message

logger = logging.getLogger(__name__)


async def write_article(
    client: LLMClient,
    writing_material: WritingMaterial,
    review: AgentCriticResult | None = None,
) -> str:
    """撰写文章

    根据提供的素材撰写文章。支持两种风格：
    1. DEEP（深度文章）：整合多篇文章，生成逻辑严密的深度观察报告
    2. FLASH（快讯）：用最简练的语言概括核心事件

    Args:
        client: AI 生成器客户端
        writing_material: 写作素材对象，包含 topic、style、match_type、
            relevance_to_focus、writing_guide、reasoning、articles 等
        review: 审查结果（可选），如果提供，将根据审查建议进行修改

    Returns:
        Markdown 格式的文章内容
    """
    prompt = _build_write_prompt(writing_material, review)
    result = await client.completion(prompt)
    return result


async def write_primary_brief(
    client: LLMClient,
    plan: dict,
    target_language: str = "zh",
) -> str:
    prompt = _build_primary_brief_prompt(plan, target_language=target_language)
    return await client.completion(prompt)


async def write_optional_section(
    client: LLMClient,
    writing_material: WritingMaterial,
) -> str:
    prompt = _build_optional_section_prompt(writing_material)
    return await client.completion(prompt)


def _build_primary_brief_prompt(plan: dict, target_language: str = "zh") -> list[Message]:
    system_prompt = Message.system(content=PRIMARY_BRIEF_SYSTEM_PROMPT)
    user_prompt = Message.user(
        content=PRIMARY_BRIEF_USER_PROMPT.format(
            target_language=target_language,
            plan=json.dumps(plan, ensure_ascii=False, indent=2),
        )
    )
    system_prompt.set_priority(0)
    user_prompt.set_priority(0)
    return [system_prompt, user_prompt]


def _build_optional_section_prompt(writing_material: WritingMaterial) -> list[Message]:
    target_language = writing_material.get("target_language", "zh")
    system_prompt = Message.system(content=OPTIONAL_SECTION_SYSTEM_PROMPT)
    user_prompt = Message.user(
        content=OPTIONAL_SECTION_USER_PROMPT.format(
            topic=writing_material["topic"],
            target_language=target_language,
            match_type=writing_material["match_type"],
            relevance_description=writing_material["relevance_description"],
            writing_guide=writing_material["writing_guide"],
            articles=json.dumps(
                writing_material["articles"],
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
        )
    )
    system_prompt.set_priority(0)
    user_prompt.set_priority(0)
    return [system_prompt, user_prompt]


def _build_write_prompt(
    writing_material: WritingMaterial, review: AgentCriticResult | None = None
) -> str | list[Message]:
    """构建写作 prompt"""
    target_language = writing_material.get("target_language", "zh")
    if writing_material["style"] == "FLASH":
        return WRITER_FLASH_NEWS_PROMPT.format(
            topic=writing_material["topic"],
            target_language=target_language,
            articles=writing_material["articles"],
        )

    ext_info = (
        writing_material["ext_info"]
        if "ext_info" in writing_material and writing_material["ext_info"]
        else []
    )
    # history_memory 现在统一为列表
    history_memories = writing_material.get("history_memory", [])
    system_prompt = Message(
        role="system",
        content=WRITER_DEEP_DIVE_SYSTEM_PROMPT_TEMPLATE.format(
            relevance_description=writing_material["relevance_description"],
            topic=writing_material["topic"],
        ),
    )
    user_prompt = Message(
        role="user",
        content=WRITER_DEEP_DIVE_USER_PROMPT_TEMPLATE.format(
            topic=writing_material["topic"],
            target_language=target_language,
            match_type=writing_material["match_type"],
            relevance_description=writing_material["relevance_description"],
            writing_guide=writing_material["writing_guide"],
            reasoning=writing_material["reasoning"],
            articles=writing_material["articles"],
            ext_info=ext_info,
            history_memories=history_memories,
            review=review if review else "",
        ),
    )
    system_prompt.set_priority(0)
    user_prompt.set_priority(0)
    return [
        system_prompt,
        user_prompt,
    ]


async def review_article(
    client: LLMClient,
    draft_content: str,
    writing_material: WritingMaterial,
) -> AgentCriticResult:
    """审查文章

    审查文章初稿，检查事实准确性、逻辑性和完整性。
    返回审查结果，包含状态（APPROVED/REJECTED）、评分、发现的问题和修改建议。
    如果发现 CRITICAL 错误，必须返回 REJECTED 状态。

    Args:
        client: AI 生成器客户端
        draft_content: 待审查的文章初稿内容（Markdown 格式）
        writing_material: 写作素材对象，用于做一致性审查

    Returns:
        审查结果
    """
    prompt = _build_review_prompt(draft_content, writing_material)

    response = await client.completion(
        prompt,
        json_format=True,
    )
    try:
        result: AgentCriticResult = extract_json(response)
        logger.info(
            "Parsed critic response successfully, status: %s", result.get("status")
        )
        return result
    except Exception as e:
        # Log a truncated version to avoid huge log entries
        # response_preview = (
        #     response[:500] + "..." if len(response) > 500 else response
        # )
        logger.error(
            "Failed to parse critic response. Error: %s\nResponse preview: %s",
            str(e),
            response,
            exc_info=True,
        )
        # print(response)
        raise ValueError(f"Failed to parse critic response: {str(e)}") from e


def _build_review_prompt(
    draft_content: str, writing_material: WritingMaterial
) -> list[Message]:
    """构建审查 prompt"""
    system_prompt = Message(role="system", content=CRITIC_SYSTEM_PROMPT_TEMPLATE)
    system_prompt.set_priority(0)
    user_prompt = Message(
        role="user",
        content=CRITIC_USER_PROMPT_TEMPLATE.format(
            draft_content=draft_content,
            articles=writing_material["articles"],
            ext_info=writing_material.get("ext_info", []),
            history_memories=writing_material.get("history_memory", []),
            target_language=writing_material.get("target_language", "zh"),
            match_type=writing_material["match_type"],
            relevance_description=writing_material["relevance_description"],
            writing_guide=writing_material["writing_guide"],
        ),
    )
    user_prompt.set_priority(0)
    return [
        system_prompt,
        user_prompt,
    ]
