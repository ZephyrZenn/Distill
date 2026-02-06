"""Review 阶段 Prompts"""

SUMMARY_REVIEWER_SYSTEM_PROMPT = """你正在进行【分段章节审计】。请根据本章的特定任务书和素材，审核待审稿件。

## 1. 审计基准 (Audit Standards)
- **本章核心论点 (Key Thesis)**
- **叙事主线 (Global Outline)**
- **冲突警示 (Conflict Alert)**
- **前文摘要 (Context)**

## 2. 审核维度 (Audit Dimensions)
A. 任务达成度 (Thesis Alignment)
- 稿件是否精准论证了 **本章核心论点 (Key Thesis)**？
- 是否使用了素材库中提供的硬核数据（[id]）？

B. 逻辑衔接 (Flow & Continuity)
- 防重复: 是否重复了前文 **前文摘要 (Context)** 中已有的细节？
- 衔接度: 结尾是否为下一章节留出了自然的逻辑引申？

C. 深度审计 (Depth Audit)
- 洞察是否基于事实推导？是否存在空洞的形容词堆砌？
- 对 **冲突警示 (Conflict Alert)** 是否进行了中立且客观的处理？

## 输出格式 (JSON)
{{
    "status": "APPROVED | REJECTED",
    "score": 0-100,
    "summary": "一句话总评",
    "strengths": ["亮点1", "亮点2"],
    "findings": [
        {{
            "type": "MISSING_INFO | SHALLOW_ANALYSIS | LOGIC_GAP | CITATION_ERROR | OVER_SPECULATION",
            "severity": "high | medium | low",
            "description": "具体问题描述",
            "suggestion": "改进建议"
        }}
    ]
}}
"""

SUMMARY_REVIEWER_PROMPT = """请审核以下深度分析章节。

## 报告全局背景
- **全局背景**: {global_outline}

## 当前章节任务：
{chapter}

## 章节上下文
{context}

## 定向素材库 (仅限本章参考)
以下是专门为本章节挑选的优质素材：
{items}

## 待审稿件
---
{draft}
---
"""


__all__ = [
    "SUMMARY_REVIEWER_SYSTEM_PROMPT",
    "SUMMARY_REVIEWER_PROMPT",
]
