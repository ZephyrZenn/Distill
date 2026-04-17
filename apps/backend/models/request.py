from datetime import datetime, time, date
from typing import Optional, Union

from pydantic import validator, Field

from .common import CamelModel
from core.models.llm import ModelProvider


def _normalize_brief_time(value: Union[time, str]) -> time:
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.strptime(text, "%H:%M")
        except ValueError as exc:
            raise ValueError("brief_time must be in HH:MM format") from exc
        return parsed.time()
    raise ValueError("brief_time must be a string or time value")


class ModifyGroupRequest(CamelModel):
    title: str
    desc: str
    feed_ids: list[int]


class ImportFeedsRequest(CamelModel):
    url: Optional[str] = None
    content: Optional[str] = None


class ModifyFeedRequest(CamelModel):
    title: str
    desc: str
    url: str


class ModelConfigRequest(CamelModel):
    """Pydantic model for model configuration in requests.

    Note: API keys are read from environment variables based on provider.
    Base URL is only required for 'other' provider.
    """

    model: str = Field(..., description="Model name")
    provider: str = Field(
        ..., description="Model provider (openai, deepseek, gemini, other)"
    )
    base_url: Optional[str] = Field(
        None, description="Base URL - only required for 'other' provider"
    )

    @validator("model", "provider")
    def validate_required_fields(cls, v):
        if not v or (isinstance(v, str) and not v.strip()):
            raise ValueError("Field cannot be empty")
        return v.strip() if isinstance(v, str) else v

    @validator("provider")
    def validate_provider(cls, v):
        try:
            ModelProvider(v)
        except ValueError as e:
            raise ValueError(f"Invalid provider: {e}")
        return v

    @validator("base_url", always=True)
    def validate_base_url(cls, v, values):
        provider = values.get("provider")
        if provider == "other":
            if not v or (isinstance(v, str) and not v.strip()):
                raise ValueError("base_url is required when provider is 'other'")
        return v.strip() if isinstance(v, str) and v else v


class RateLimitSettingRequest(CamelModel):
    requests_per_minute: Optional[float] = None
    burst_size: Optional[int] = None
    enable_rate_limit: Optional[bool] = None
    max_retries: Optional[int] = None
    base_delay: Optional[float] = None
    max_delay: Optional[float] = None
    enable_retry: Optional[bool] = None


class ContextSettingRequest(CamelModel):
    max_tokens: Optional[int] = None
    compress_threshold: Optional[float] = None


class AgentLimitsSettingRequest(CamelModel):
    max_iterations: Optional[int] = None
    max_tool_calls: Optional[int] = None
    max_curations: Optional[int] = None
    max_plan_reviews: Optional[int] = None
    max_refines: Optional[int] = None
    enable_hard_limits: Optional[bool] = None


class EmbeddingSettingRequest(CamelModel):
    model: str = Field(..., description="Embedding model name")
    provider: str = Field(..., description="Provider (openai, deepseek, gemini, other)")
    base_url: Optional[str] = Field(None, description="Base URL for 'other' provider")

    @validator("model", "provider")
    def validate_required_fields(cls, v):
        if not v or (isinstance(v, str) and not v.strip()):
            raise ValueError("Field cannot be empty")
        return v.strip() if isinstance(v, str) else v

    @validator("provider")
    def validate_provider(cls, v):
        try:
            ModelProvider(v)
        except ValueError as e:
            raise ValueError(f"Invalid provider: {e}") from e
        return v


class ModifySettingRequest(CamelModel):
    model: Optional[ModelConfigRequest] = None
    lightweight_model: Optional[ModelConfigRequest] = None
    embedding: Optional[EmbeddingSettingRequest] = None
    rate_limit: Optional[RateLimitSettingRequest] = None
    context: Optional[ContextSettingRequest] = None
    agent_limits: Optional[AgentLimitsSettingRequest] = None


class CreateScheduleRequest(CamelModel):
    time: str  # HH:MM format
    focus: str
    group_ids: list[int]
    auto_expand: bool = False

    @validator("time")
    def validate_time(cls, value):
        return _normalize_brief_time(value)

    @validator("group_ids")
    def validate_group_ids(cls, value):
        if not value:
            raise ValueError("group_ids cannot be empty")
        return value


class UpdateScheduleRequest(CamelModel):
    time: Optional[str] = None  # HH:MM format
    focus: Optional[str] = None
    group_ids: Optional[list[int]] = None
    enabled: Optional[bool] = None
    auto_expand: Optional[bool] = None

    @validator("time")
    def validate_time(cls, value):
        if value is None:
            return value
        return _normalize_brief_time(value)

    @validator("group_ids")
    def validate_group_ids(cls, value):
        if value is not None and len(value) == 0:
            raise ValueError("group_ids cannot be empty")
        return value


class GetBriefsRequest(CamelModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
