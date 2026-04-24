"""Task management router for async brief generation."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Literal, Optional
import asyncio

from apps.backend.models.common import success_with_data
from apps.backend.services import task_service

router = APIRouter(prefix="/tasks", tags=["task"])

class CreateTaskRequest(BaseModel):
    group_ids: list[int]
    focus: str = ""
    ui_language: Literal["zh", "en"] = "zh"

@router.post("/")
async def create_task(request: CreateTaskRequest):
    """创建brief生成任务并立即返回任务ID"""
    if not request.group_ids:
        raise HTTPException(status_code=400, detail="group_ids cannot be empty")
    
    task_id = task_service.create_task(
        group_ids=request.group_ids,
        focus=request.focus,
        ui_language=request.ui_language,
    )
    
    # 在后台异步执行brief生成任务
    asyncio.create_task(task_service.execute_brief_generation_task(task_id))
    
    return success_with_data({"task_id": task_id})

@router.get("/{task_id}")
async def get_task_status(task_id: str):
    """获取任务状态和日志"""
    task = task_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return success_with_data(task.to_dict())

@router.get("/stats/summary")
async def get_task_stats():
    """获取任务统计信息"""
    stats = task_service.get_task_count()
    return success_with_data(stats)
