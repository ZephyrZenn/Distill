from datetime import datetime
from typing import Callable, Literal, TypedDict
from typing_extensions import NotRequired

from agent.tracing import TraceEvent, render_trace_message
from core.models.feed import FeedGroup
from core.models.search import SearchResult

# 步骤回调函数类型
StepCallback = Callable[[str], None]


class RawArticle(TypedDict):
    id: str
    title: str
    url: str
    summary: str
    pub_date: datetime
    content: NotRequired[str]


class Article(TypedDict):
    id: str
    title: str
    url: str
    summary: str
    pub_date: datetime
    content: NotRequired[str]
    score: float
    reasoning: str


GenerationMode = Literal["BRIEF_ONLY", "OPTIONAL_DEEP", "AUTO_DEEP"]


class DailyBriefItem(TypedDict):
    title: str
    summary: str
    importance: str
    article_ids: list[str]


class FocalPoint(TypedDict):
    """规划阶段产出的焦点主题结构，可附加分层工作流的可选后处理元数据。"""

    priority: int
    topic: str
    # FOCUS_MATCH | GLOBAL_STRATEGIC | HISTORICAL_CONTINUITY
    match_type: Literal["FOCUS_MATCH", "GLOBAL_STRATEGIC", "HISTORICAL_CONTINUITY"]
    # 解释该专题如何匹配用户关注点（若无 focus 则可为 N/A）
    relevance_description: str
    strategy: Literal["SUMMARIZE", "SEARCH_ENHANCE", "FLASH_NEWS"]
    article_ids: list[str]
    reasoning: str
    search_query: str
    writing_guide: str
    # 历史记忆的 id 列表（如果延续自历史记忆，则给出历史记忆的 id，否则为空列表）
    history_memory_id: list[int]
    generation_mode: NotRequired[GenerationMode]
    topic_overview: NotRequired[str]
    deep_analysis_reason: NotRequired[str]
    auto_deep_exception: NotRequired[str]


class DiscardedItem(TypedDict):
    id: str
    reason: str


class AgentPlanResult(TypedDict):
    today_pattern: str
    daily_overview: NotRequired[str]
    daily_brief_items: NotRequired[list[DailyBriefItem]]
    focal_points: list[FocalPoint]
    discarded_items: list[DiscardedItem]


class ExpandableTopic(TypedDict):
    topic_id: str
    focal_point: FocalPoint


class SummaryMemory(TypedDict):
    id: int
    topic: str
    reasoning: str
    content: str


class WritingMaterial(TypedDict):
    topic: str
    style: Literal["DEEP", "FLASH"]
    match_type: Literal["FOCUS_MATCH", "GLOBAL_STRATEGIC", "HISTORICAL_CONTINUITY"]
    relevance_description: str
    writing_guide: str
    reasoning: str
    articles: list[Article]
    ext_info: NotRequired[list[SearchResult]]
    history_memory: NotRequired[list[SummaryMemory]]
    target_language: NotRequired[Literal["zh", "en"]]


class AgentState(TypedDict):
    focus: str
    target_language: NotRequired[Literal["zh", "en"]]
    ui_language: NotRequired[Literal["zh", "en"]]
    groups: list[FeedGroup]
    raw_articles: list[RawArticle]
    scored_articles: list[Article]
    plan: NotRequired[AgentPlanResult]
    expandable_topics: NotRequired[list[ExpandableTopic]]
    writing_materials: NotRequired[list[WritingMaterial]]
    summary_results: NotRequired[list[str]]
    execution_status: NotRequired[
        list[bool]
    ]  # 每个任务的执行状态，与 summary_results 一一对应
    log_history: list[str]
    on_step: NotRequired[StepCallback]
    history_memories: dict[int, SummaryMemory]
    ext_info: NotRequired[list[SearchResult]]  # 收集所有使用的外部搜索结果
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED"]
    created_at: datetime


def log_step(state: "AgentState", message: str | TraceEvent) -> None:
    """记录执行步骤到历史，并触发回调（如果有）"""
    localized_message = render_trace_message(message, state.get("ui_language"))
    state["log_history"].append(localized_message)
    if "on_step" in state and state["on_step"]:
        state["on_step"](localized_message)


class AgentCriticFinding(TypedDict):
    severity: Literal["CRITICAL", "ADVISORY"]
    type: Literal[
        "FACT_ERROR",
        "MISSING_INFO",
        "HALLUCINATION",
        "INTENT_MISMATCH",
        "LAZY_REWRITE",
        "LOGIC_WEAKNESS",
        "OVER_SPECULATION",
        "REFERENCE_ERROR",
    ]
    location: str
    correction_suggestion: str


class AgentCriticResult(TypedDict):
    status: Literal["APPROVED", "REJECTED"]
    score: int
    findings: list[AgentCriticFinding]
    overall_comment: str


class StructureFocalPoint(TypedDict):
    """Refined focal point for the Structure Phase, separating sources explicitly."""

    priority: int
    topic: str
    match_type: Literal["FOCUS_MATCH", "GLOBAL_STRATEGIC", "HISTORICAL_CONTINUITY"]
    relevance_to_focus: str
    strategy: Literal["DEEP_DIVE", "FLASH_NEWS"]
    rss_ids: list[str]
    web_ids: list[str]
    memory_ids: list[str]
    reasoning: str
    writing_guide: str


class StructurePlanResult(TypedDict):
    daily_overview: str
    focal_points: list[StructureFocalPoint]
