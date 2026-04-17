from fastapi import APIRouter, HTTPException

from apps.backend.models.common import success_with_data
from apps.backend.models.request import CreateScheduleRequest, UpdateScheduleRequest
from apps.backend.models.view_model import ScheduleListResponse, ScheduleResponse, ScheduleVO
from apps.backend.services.scheduler_service import (
    get_all_schedules as get_all_schedules_service,
    get_schedule as get_schedule_service,
    create_schedule as create_schedule_service,
    update_schedule as update_schedule_service,
    delete_schedule as delete_schedule_service,
)

router = APIRouter(prefix="/schedules", tags=["schedule"])


@router.get("/", response_model=ScheduleListResponse)
async def get_all_schedules():
    """Get all schedules."""
    schedules = get_all_schedules_service()
    schedule_vos = [
        ScheduleVO(
            id=s.id,
            time=s.time.strftime("%H:%M"),
            focus=s.focus,
            group_ids=s.group_ids,
            enabled=s.enabled,
            auto_expand=s.auto_expand,
        )
        for s in schedules
    ]
    return success_with_data(schedule_vos)


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(schedule_id: str):
    """Get a schedule by ID."""
    schedule = get_schedule_service(schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    return success_with_data(
        ScheduleVO(
            id=schedule.id,
            time=schedule.time.strftime("%H:%M"),
            focus=schedule.focus,
            group_ids=schedule.group_ids,
            enabled=schedule.enabled,
            auto_expand=schedule.auto_expand,
        )
    )


@router.post("/", response_model=ScheduleResponse)
async def create_schedule(request: CreateScheduleRequest):
    """Create a new schedule."""
    schedule = create_schedule_service(
        time_str=request.time,
        focus=request.focus,
        group_ids=request.group_ids,
        auto_expand=request.auto_expand,
    )

    return success_with_data(
        ScheduleVO(
            id=schedule.id,
            time=schedule.time.strftime("%H:%M"),
            focus=schedule.focus,
            group_ids=schedule.group_ids,
            enabled=schedule.enabled,
            auto_expand=schedule.auto_expand,
        )
    )


@router.put("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(schedule_id: str, request: UpdateScheduleRequest):
    """Update an existing schedule."""
    schedule = update_schedule_service(
        schedule_id=schedule_id,
        time_str=request.time,
        focus=request.focus,
        group_ids=request.group_ids,
        enabled=request.enabled,
        auto_expand=request.auto_expand,
    )

    if not schedule:
        raise HTTPException(status_code=404, detail="Schedule not found")

    return success_with_data(
        ScheduleVO(
            id=schedule.id,
            time=schedule.time.strftime("%H:%M"),
            focus=schedule.focus,
            group_ids=schedule.group_ids,
            enabled=schedule.enabled,
            auto_expand=schedule.auto_expand,
        )
    )


@router.delete("/{schedule_id}")
async def delete_schedule(schedule_id: str):
    """Delete a schedule."""
    success = delete_schedule_service(schedule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Schedule not found")
    return success_with_data(None)

