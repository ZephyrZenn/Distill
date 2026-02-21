from __future__ import annotations
from dataclasses import dataclass, field
from typing import TypedDict, Literal, NotRequired


class ResearchItem(TypedDict, total=False):
    """A normalized research record used for ranking."""

    id: str
    title: str
    url: str
    source: str  # feed | web | memory
    published_at: str
    summary: str
    content: str
    tags: list[str]

    # Five-dimensional scoring (stored during curation)
    relevance: float  # Focus + bucket similarity (0.0-1.0)
    quality: float  # Content richness (0.0-1.0)
    novelty: float  # Information gain (0.0-1.0)
    score: float

    # LLM audit fields (P0: Two-stage audit)
    audit_stage: NotRequired[Literal["snippet", "full", "none"]]  # Current audit stage
    should_fetch_full: NotRequired[bool]  # Whether to fetch full content for Stage 2
    audit_reason: NotRequired[str]  # Reason for discard/keep from LLM


class DiscardedItem(TypedDict, total=False):
    """An item that was dropped during curation, with a reason."""

    id: str
    title: str
    url: str
    reason: str


@dataclass
class Dimension:
    """研究意图维度.

    描述从什么角度收集信息，用于指导搜索和 LLM 审计。
    """

    type: Literal[
        "technical_facts",
        "market_competition",
        "financial_performance",
        "use_cases",
        "historical_evolution",
        "future_outlook",
        "geopolitical",
        "societal_impact",
        "other",
    ]
    name: str
    """维度名称（简洁描述）"""

    intent: str
    """研究意图：我们需要从什么角度收集信息？"""

    keywords: list[str] = field(default_factory=list)
    """用于搜索的关键词"""

    priority: Literal["critical", "high", "medium", "low"] = "medium"
    """优先级"""

    relevance_criteria: str = ""
    """如何判断一篇文章是否与这个维度相关？"""

    def to_dict(self) -> dict:
        """转换为字典格式（用于与 LLM 交互）."""
        return {
            "type": self.type,
            "name": self.name,
            "intent": self.intent,
            "keywords": self.keywords,
            "priority": self.priority,
            "relevance_criteria": self.relevance_criteria,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Dimension":
        """从字典创建 Dimension 实例."""
        return cls(
            type=data.get("type", "other"),
            name=data.get("name", ""),
            intent=data.get("intent", ""),
            keywords=data.get("keywords", []),
            priority=data.get("priority", "medium"),
            relevance_criteria=data.get("relevance_criteria", ""),
        )


class PatchDiagnosis(TypedDict):
    """补丁诊断（用于 PATCH_MODE：增强搜索）

    类似 AuditFeedback，专注于指导下一轮搜索。
    """

    suggested_queries: list[str]  # 建议的补丁查询（用于生成搜索）
    missing_entities: list[str]  # 缺失的关键实体/主题
    coverage_gaps: list[str]  # 覆盖缺口描述
    coverage_score: float  # 覆盖度评分 0.0-1.0
    action_reason: str  # 补丁原因


class ReplanDiagnosis(TypedDict):
    """重规划诊断（用于 REPLAN_MODE：重新定义研究维度）

    当搜索方向存在根本性问题时，重新生成研究维度。
    """

    new_directions: dict  # 新的研究方向指引
    # 格式: {"废弃方向": "原因", "新方向": "建议"}

    replan_justification: str  # 重规划理由
    failed_dimensions: list[str]  # 失败的维度名称（需废弃）
    suggested_pivots: list[str]  # 建议的研究转向

    # 兼容字段
    coverage_score: float  # 当前覆盖度评分
    action_reason: str  # 简述原因


class LoopLimits(TypedDict):
    """循环限制配置"""

    max_patch_per_dimension: int  # 最大补丁次数 (default: 2)
    max_replan: int  # 最大重规划次数 (default: 2)


class AuditAnalysisResult(TypedDict):
    is_sufficient: bool
    reason: str
    coverage_gaps: list[str]
    search_pivot: str | None
    suggested_queries: list[str]


class SnippetAuditResult(TypedDict):
    id: str
    action: Literal["keep", "discard"]
    relevance_score: float
    reasoning: SnippetAuditReasoning
    explanation: str
    should_fetch_full: bool


class SnippetAuditReasoning(TypedDict):
    topic_match: Literal["Yes", "Partial", "No"]
    matched_dimensions: list[str]
    information_value: Literal["High", "Medium", "Low"]
    red_flags: list[str]


class FullAuditResult(TypedDict):
    id: str
    action: Literal["keep", "discard"]
    scores: FullAuditScores
    audit_report: FullAuditReport


class FullAuditScores(TypedDict):
    refined_relevance: float
    quality_score: float
    novelty_score: float


class FullAuditReport(TypedDict):
    key_findings: list[str]
    reason: str
    defects: str


class PlanReviewResult(TypedDict):
    status: Literal["READY", "PATCH", "REPLAN"]
    reason: str
    coverage_score: float
    high_quality_ratio: float
    key_findings: list[str]
    conflicts: list[str]
    gaps: list[str]
    patch_query: str
    key_items: list[str]
    new_directions: list[dict]
    failed_dimensions: list[dict]


class StructureChapter(TypedDict):
    chapter_id: str  # 章节ID
    title: str  # 章节名称
    priority: int  # 章节优先级
    key_thesis: str  # 本章试图证明的核心论点
    writing_guide: dict  # 写作指南
    referenced_doc_ids: list[str]  # 指定该章节使用的素材ID
    conflict_alert: (
        str  # 若本章存在素材冲突，请说明（如：关于2025年销量的预测存在两种分歧）
    )
    sub_points: list[str]  # 子论点列表


class StructurePlan(TypedDict):
    daily_overview: str
    narrative_logic: (
        str  # 简述本报告的叙事主线（例如：从供应链瓶颈推导至终端价格波动的因果链条）
    )
    chapters: list[StructureChapter]  # 章节列表


class WritingMaterial(TypedDict):
    chapter: StructureChapter
    items: list[ResearchItem]


class WritingContext(TypedDict):
    global_outline: str
    previous_summary: str
    section_number: int


class SectionUnit(TypedDict):
    chapter: StructureChapter
    items: list[ResearchItem]
    content: str
    context: WritingContext
    review_result: NotRequired[ReviewResult]


class ReviewFinding(TypedDict):
    type: Literal[
        "MISSING_INFO",
        "SHALLOW_ANALYSIS",
        "LOGIC_GAP",
        "CITATION_ERROR",
        "OVER_SPECULATION",
    ]
    severity: Literal["high", "medium", "low"]
    description: str
    suggestion: str


class ReviewResult(TypedDict):
    status: Literal["APPROVED", "REJECTED"]
    score: int
    summary: str
    strengths: list[str]
    findings: list[ReviewFinding]


__all__ = [
    "Dimension",
    "PatchDiagnosis",
    "ReplanDiagnosis",
    "LoopLimits",
    "AuditAnalysisResult",
    "SnippetAuditResult",
    "FullAuditResult",
    "FullAuditScores",
    "FullAuditReport",
    "PlanReviewResult",
    "StructureChapter",
    "StructurePlan",
    "ReviewResult",
    "ReviewFinding",
    "ResearchItem",
]
