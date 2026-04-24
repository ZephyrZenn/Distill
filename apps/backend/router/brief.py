
from datetime import date
from fastapi import APIRouter, Query, HTTPException
from typing import Literal, Optional
from pydantic import BaseModel
import asyncio

from apps.backend.models.common import success_with_data
from apps.backend.models.view_model import (
    FeedBriefListResponse,
    FeedBriefResponse,
    GenerateBriefResponse,
    BriefGenerationStatusResponse,
)
from apps.backend.services import brief_service, group_service, task_service

router = APIRouter(prefix="/briefs")


class GenerateBriefRequest(BaseModel):
    group_ids: list[int]
    focus: str = ""
    agent_mode: bool = False
    ui_language: Literal["zh", "en"] = "zh"


@router.get("/", response_model=FeedBriefListResponse)
async def get_briefs(
    start_date: Optional[str] = Query(None, description="开始日期，格式：YYYY-MM-DD，默认为当日"),
    end_date: Optional[str] = Query(None, description="结束日期，格式：YYYY-MM-DD，默认为当日")
):
    """
    Get briefs between two dates. If no dates provided, returns today's briefs.
    列表接口不返回完整内容（content 和 ext_info），只返回基本信息。
    """
    # 如果未提供日期，默认使用今天
    today = date.today()
    start = date.fromisoformat(start_date) if start_date else today
    end = date.fromisoformat(end_date) if end_date else today
    
    # 列表接口不包含完整内容
    briefs = brief_service.get_briefs(start, end, include_content=False)
    group_ids = list({group_id for brief in briefs for group_id in brief.group_ids})
    groups = group_service.get_groups(group_ids)
    return success_with_data([brief.to_view_model(groups, include_content=False) for brief in briefs])


@router.get("/{brief_id}", response_model=FeedBriefResponse)
async def get_brief_detail(brief_id: int):
    """
    获取单个简报的完整信息，包含 content 和 ext_info。
    """
    brief = brief_service.get_brief_by_id(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")

    group_ids = brief.group_ids
    groups = group_service.get_groups(group_ids)
    return success_with_data(brief.to_view_model(groups, include_content=True))


@router.post("/{brief_id}/expand/{topic_id}", status_code=202)
async def expand_optional_topic(brief_id: int, topic_id: str):
    brief = brief_service.get_brief_by_id(brief_id)
    if not brief:
        raise HTTPException(status_code=404, detail="Brief not found")
    topic = next(
        (t for t in (brief.expandable_topics or []) if t.get("topic_id") == topic_id),
        None,
    )
    if not topic:
        raise HTTPException(status_code=404, detail="Expandable topic not found")
    asyncio.create_task(brief_service.expand_optional_topic(brief_id, topic_id))
    return {"message": "expansion started"}


@router.get("/{brief_id}/expanding")
async def get_expanding_topics(brief_id: int):
    return success_with_data(brief_service.get_expanding_topic_ids(brief_id))


@router.post("/generate", response_model=GenerateBriefResponse)
async def generate_brief(request: GenerateBriefRequest):
    """
    异步生成brief，立即返回任务ID用于轮询状态。
    """
    # AgentMode 需要填写 focus
    if request.agent_mode and not request.focus.strip():
        raise HTTPException(status_code=400, detail="focus cannot be empty when agent_mode is true")

    # AgentMode 不需要 group_ids，原模式需要至少一个分组
    if not request.agent_mode and not request.group_ids:
        raise HTTPException(status_code=400, detail="group_ids cannot be empty when agent_mode is false")

    # 创建任务
    task_id = task_service.create_task(
        group_ids=request.group_ids if request.group_ids else [],
        focus=request.focus.strip(),
        agent_mode=request.agent_mode,
        ui_language=request.ui_language,
    )

    # 在后台异步执行brief生成任务
    asyncio.create_task(task_service.execute_brief_generation_task(task_id))

    return success_with_data({"task_id": task_id})


@router.get("/generate/{task_id}", response_model=BriefGenerationStatusResponse)
async def get_generation_status(task_id: str):
    """
    获取brief生成任务的状态和日志。
    """
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return success_with_data(task.to_dict())
