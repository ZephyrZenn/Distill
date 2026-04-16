from datetime import datetime
from typing import List, Optional

from .common import CamelModel, CommonResult
from core.config.defaults import DEFAULT_AGENT_LIMITS as _AGENT_LIMITS_DEFAULTS


class FeedVO(CamelModel):
    id: int
    title: str
    url: str
    desc: str
    status: str


class FeedGroupVO(CamelModel):
    id: int
    title: str
    desc: str
    feeds: List[FeedVO]


class FeedBriefVO(CamelModel):
    id: int
    groups: List[FeedGroupVO]
    content: Optional[str] = None  # 列表接口不返回，详情接口返回
    pub_date: datetime
    summary: Optional[str] = None  # 概要（二级标题列表）
    overview: Optional[str] = None  # 日报概览（来自 plan 的 daily_overview）
    ext_info: Optional[List[dict]] = None  # 外部搜索结果，列表接口不返回，详情接口返回
    expandable_topics: Optional[List[dict]] = None


class ModelSettingVO(CamelModel):
    """Model setting view object.

    Note: API keys are managed via environment variables, not exposed in API.
    Base URL is only present for 'other' provider.
    """

    model: str
    provider: str
    base_url: Optional[str] = None  # Only present for 'other' provider
    api_key_configured: bool = False  # Whether the API key is configured
    api_key_env_var: str = ""  # Environment variable name for the API key


class RateLimitSettingVO(CamelModel):
    """Rate limit and retry settings (advanced)."""

    requests_per_minute: float = 60.0
    burst_size: int = 10
    enable_rate_limit: bool = True
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    enable_retry: bool = True


class ContextSettingVO(CamelModel):
    """Context window settings (advanced)."""

    max_tokens: int = 128000
    compress_threshold: float = 0.8


class AgentLimitsSettingVO(CamelModel):
    """Agent loop limits (advanced)."""

    max_iterations: int = _AGENT_LIMITS_DEFAULTS.max_iterations
    max_tool_calls: int = _AGENT_LIMITS_DEFAULTS.max_tool_calls
    max_curations: int = _AGENT_LIMITS_DEFAULTS.max_curations
    max_plan_reviews: int = _AGENT_LIMITS_DEFAULTS.max_plan_reviews
    max_refines: int = _AGENT_LIMITS_DEFAULTS.max_refines
    enable_hard_limits: bool = _AGENT_LIMITS_DEFAULTS.enable_hard_limits


class EmbeddingSettingVO(CamelModel):
    """Embedding config (API key from EMBEDDING_API_KEY env)."""

    model: str
    provider: str
    base_url: Optional[str] = None
    api_key_configured: bool = False
    api_key_env_var: str = "EMBEDDING_API_KEY"


class SettingVO(CamelModel):
    model: ModelSettingVO
    lightweight_model: Optional[ModelSettingVO] = None
    embedding: Optional[EmbeddingSettingVO] = None
    tavily_configured: bool = False  # TAVILY_API_KEY for web search (Agent)
    rate_limit: Optional[RateLimitSettingVO] = None
    context: Optional[ContextSettingVO] = None
    agent_limits: Optional[AgentLimitsSettingVO] = None


class ScheduleVO(CamelModel):
    id: str
    time: str  # HH:MM format
    focus: str
    group_ids: List[int]
    enabled: bool


class FeedBriefResponse(CommonResult[FeedBriefVO]):
    pass


class FeedBriefListResponse(CommonResult[List[FeedBriefVO]]):
    pass


class FeedGroupListResponse(CommonResult[List[FeedGroupVO]]):
    pass


class FeedGroupDetailResponse(CommonResult[FeedGroupVO]):
    pass


class FeedListResponse(CommonResult[List[FeedVO]]):
    pass


class SettingResponse(CommonResult[SettingVO]):
    pass


class AgentCheckVO(CamelModel):
    """Agent 模式配置检查结果"""

    ready: bool  # 配置是否齐全
    missing: List[str]  # 缺失项描述（如未配置的 API Key 等）


class AgentCheckResponse(CommonResult[AgentCheckVO]):
    pass


class ScheduleListResponse(CommonResult[List[ScheduleVO]]):
    pass


class ScheduleResponse(CommonResult[ScheduleVO]):
    pass


class GenerateBriefResponse(CommonResult[dict]):
    """生成任务创建响应"""

    pass


class BriefGenerationStatusResponse(CommonResult[dict]):
    """生成任务状态响应"""

    pass


class OptionalTopicExpansionVO(CamelModel):
    brief_id: int
    topic_id: str
    topic: str
    content: str
    ext_info: Optional[List[dict]] = None


class OptionalTopicExpansionResponse(CommonResult[OptionalTopicExpansionVO]):
    pass
