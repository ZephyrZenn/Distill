import logging
import re
import json
from agent.ps_agent.prompts.bootstrap import (
    BOOTSTRAP_REPLAN_PROMPT,
)
from core.llm_client import LLMClient
from agent.ps_agent.state import PSAgentState, log_step
from agent.ps_agent.prompts import (
    BOOTSTRAP_INTENT_DIMENSIONS_PROMPT,
    BOOTSTRAP_SYSTEM_PROMPT,
    BOOTSTRAP_EXCLUSION_PROMPT,
    build_bootstrap_user_prompt,
)
from agent.utils import extract_json
from core.models.llm import Message
from agent.ps_agent.models import Dimension, ReplanDiagnosis

logger = logging.getLogger(__name__)


async def _generate_intent_dimensions(
    focus: str,
    client: LLMClient,
    is_replan: bool = False,
    replan_diagnosis: ReplanDiagnosis | None = None,
) -> list[Dimension]:
    """使用 LLM 生成研究意图维度.

    Args:
        focus: 用户输入的关注点
        client: LLM client
        is_replan: 是否为重规划模式
        replan_context: 重规划上下文（包含 new_directions 等）

    Returns:
        意图维度列表
    """
    try:
        if is_replan and replan_diagnosis:
            # REPLAN 模式：使用重规划 prompt
            new_directions = replan_diagnosis.get("new_directions", [])
            replan_justification = replan_diagnosis.get("replan_justification", "")
            new_directions_json = json.dumps(
                new_directions, ensure_ascii=False, indent=2
            )
            failed_dimensions = replan_diagnosis.get("failed_dimensions", [])
            failed_dimensions_json = json.dumps(
                failed_dimensions, ensure_ascii=False, indent=2
            )

            replan_user_prompt = f"""Focus: {focus}

## Replan Context

### Replan Justification
{replan_justification}

### New Directions (为维度重新定义提供指导)
```json
{new_directions_json}

### Failed Dimensions (为废弃的维度提供指导)
```json
{failed_dimensions_json}
```

请根据以上信息，重新生成研究意图维度。
"""
            messages = [
                Message.system(BOOTSTRAP_REPLAN_PROMPT).set_priority(0),
                Message.user(replan_user_prompt).set_priority(0),
            ]
        else:
            # 正常模式：直接生成意图维度
            messages = [
                Message.system(BOOTSTRAP_INTENT_DIMENSIONS_PROMPT).set_priority(0),
                Message.user(f"Focus: {focus}").set_priority(0),
            ]

        response = await client.completion(messages)
        data = extract_json(response)
        dimensions_dict = data.get("dimensions", [])

        # 转换为 Dimension 对象
        dimensions = [Dimension.from_dict(d) for d in dimensions_dict]

        logger.info(
            "[bootstrap] Generated %d intent dimensions: %s",
            len(dimensions),
            ", ".join([f"{d.name}(priority={d.priority})" for d in dimensions[:3]]),
        )
        return dimensions

    except Exception as exc:
        logger.warning(f"[bootstrap] Failed to generate intent dimensions: {exc}")
        return []


async def _generate_negative_keywords(
    focus: str,
    focus_dimensions: list[Dimension],
    client: LLMClient,
) -> list[str]:
    """使用 LLM 生成排除关键词.

    Args:
        focus: 用户输入的关注点
        focus_dimensions: 研究意图维度
        client: LLM client

    Returns:
        排除关键词列表
    """
    try:
        # 转换 Dimension 对象为字典用于 JSON 序列化
        dimensions_dict = [d.to_dict() for d in focus_dimensions]
        exclusion_messages = [
            Message.system(BOOTSTRAP_EXCLUSION_PROMPT).set_priority(0),
            Message.user(
                f"Focus: {focus}\n"
                f"Dimensions: {json.dumps(dimensions_dict, ensure_ascii=False)}"
            ).set_priority(0),
        ]
        response = await client.completion(exclusion_messages)
        data = extract_json(response)
        exclusions = data.get("exclusions", [])

        negative_keywords = []
        for exc in exclusions:
            negative_keywords.extend(exc.get("excluded_keywords", []))

        # 去重
        negative_keywords = list(set(negative_keywords))

        logger.info(
            "[bootstrap] Extracted %d exclusion keywords",
            len(negative_keywords),
        )
        return negative_keywords

    except Exception as exc:
        logger.warning(f"[bootstrap] Failed to extract exclusions: {exc}")
        return []


class BootstrapNode:
    """Bootstrap 节点：初始化研究框架，生成意图维度和排除规则。"""

    def __init__(self, client: LLMClient):
        self.client = client

    async def __call__(self, state: PSAgentState) -> dict:
        focus = state["focus"].strip()
        is_replan = state.get("execution_mode") == "REPLAN_MODE"

        run_id = state.get("run_id", "-")
        log_step(
            state,
            "📌 bootstrap: 正在初始化研究维度与排除规则..."
            + (" (REPLAN)" if is_replan else ""),
        )
        logger.info(
            "[ps_agent] run_id=%s node=bootstrap entry focus=%s date=%s is_replan=%s",
            run_id, focus[:64] if focus else "", state["current_date"], is_replan,
        )

        # TODO: replan 结构统一
        replan_diagnosis = state.get("replan_diagnosis")
        focus_dimensions = await _generate_intent_dimensions(
            focus=focus,
            client=self.client,
            is_replan=is_replan,
            replan_diagnosis=replan_diagnosis,
        )
        log_step(state, "📌 bootstrap: 已生成研究维度，正在生成排除关键词...")

        # 生成排除关键词
        negative_keywords = await _generate_negative_keywords(
            focus=focus,
            focus_dimensions=focus_dimensions,
            client=self.client,
        )

        # 5. 构建消息（包含研究框架摘要）
        messages = [
            Message.system(BOOTSTRAP_SYSTEM_PROMPT).set_priority(0),
            Message.user(
                build_bootstrap_user_prompt(
                    focus=focus, current_date=state["current_date"]
                )
            ).set_priority(0),
        ]
        framework_summary = _build_framework_summary(
            focus_dimensions=focus_dimensions,
            negative_keywords=negative_keywords,
        )
        messages.append(Message.assistant(framework_summary).set_priority(0))

        # 6. REPLAN_MODE 特殊处理
        if is_replan:
            replan_count = state.get("replan_count", 0) + 1
            logger.info(
                f"[bootstrap] REPLAN_MODE detected, processing replan (replan_count={replan_count})"
            )

            log_step(
                state,
                f"[bootstrap] 完成: REPLAN 完成，重新生成 {len(focus_dimensions)} 个意图维度",
            )
            return {
                "messages": messages,
                "focus_dimensions": focus_dimensions,
                "negative_keywords": negative_keywords,
                "research_items": [],  # REPLAN 清空旧素材重新收集
                "replan_count": replan_count,
                "execution_mode": "NORMAL",
                "replan_diagnosis": None,  # 消费掉 report
                "status": "research",
                "last_error": None,
            }

        # 7. Normal bootstrap
        log_step(
            state,
            f"[bootstrap] 完成: 已建立研究框架 focus='{focus}' dimensions={len(focus_dimensions)}",
        )
        return {
            "messages": messages,
            "focus_dimensions": focus_dimensions,
            "negative_keywords": negative_keywords,
            "status": "research",
            "last_error": None,
        }


def _build_framework_summary(
    focus_dimensions: list[Dimension],
    negative_keywords: list[str],
) -> str:
    """构建研究框架摘要，作为全局上下文锚点传递给后续节点。"""
    lines = ["## 研究框架已建立", ""]

    # 1. 研究意图维度
    if focus_dimensions:
        # 按优先级分组
        critical_dims = [d for d in focus_dimensions if d.priority == "critical"]
        high_dims = [d for d in focus_dimensions if d.priority == "high"]
        other_dims = [
            d for d in focus_dimensions if d.priority not in ("critical", "high")
        ]

        lines.append(f"### 研究意图维度 ({len(focus_dimensions)}个)")
        if critical_dims:
            lines.append("**核心维度** (critical - 必须收集):")
            for d in critical_dims:
                lines.append(f"- **{d.name}**: {d.intent[:80]}...")
        if high_dims:
            lines.append("**重要维度** (high - 尽量收集):")
            for d in high_dims:
                lines.append(f"- **{d.name}**: {d.intent[:80]}...")
        if other_dims:
            lines.append("**补充维度** (medium/low):")
            for d in other_dims:
                lines.append(f"- **{d.name}**: {d.intent[:60]}...")
        lines.append("")

    # 2. 排除规则
    if negative_keywords:
        preview = ", ".join(negative_keywords[:8])
        if len(negative_keywords) > 8:
            preview += f" ... (共{len(negative_keywords)}个)"
        lines.append("### 排除规则")
        lines.append(f"需排除的关键词: {preview}")
        lines.append("")

    lines.append("接下来将按照此框架进行定向素材收集。")
    return "\n".join(lines)
