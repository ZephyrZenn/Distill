"""Scheduler management utilities for brief generation."""

import logging
import uuid
from datetime import time
from typing import List, Optional, Tuple, Union

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from apps.backend.crons import generate_scheduled_brief
from core.db.pool import get_connection

logger = logging.getLogger(__name__)

_scheduler: Optional[AsyncIOScheduler] = None


class Schedule:
    """Internal schedule model."""

    def __init__(
        self,
        id: str,
        time: time,
        focus: str,
        group_ids: List[int],
        enabled: bool = True,
    ):
        self.id = id
        self.time = time
        self.focus = focus
        self.group_ids = group_ids
        self.enabled = enabled

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "time": self.time.strftime("%H:%M"),
            "focus": self.focus,
            "group_ids": self.group_ids,
            "enabled": self.enabled,
        }

    @classmethod
    def from_db_row(cls, row: tuple) -> "Schedule":
        """Create Schedule from database row (id, time, focus, group_ids, enabled)."""
        return cls(
            id=row[0],
            time=row[1],
            focus=row[2],
            group_ids=list(row[3]) if row[3] else [],
            enabled=row[4],
        )


def _get_scheduler() -> AsyncIOScheduler:
    """Lazily instantiate and return the global scheduler."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def _start_if_needed() -> None:
    scheduler = _get_scheduler()
    if not scheduler.running:
        scheduler.start()


def init_scheduler() -> None:
    """Initialize and start the scheduler. Should be called at application startup."""
    scheduler = _get_scheduler()
    if not scheduler.running:
        scheduler.start()
        logger.info("Scheduler started")


def _parse_brief_time(brief_time: Union[str, time]) -> Tuple[int, int]:
    """Convert a supported time representation into hour/minute integers."""
    if isinstance(brief_time, time):
        return brief_time.hour, brief_time.minute

    hour_str, minute_str = brief_time.split(":", maxsplit=1)
    return int(hour_str), int(minute_str)


def shutdown_scheduler() -> None:
    """Shutdown the scheduler if it is running."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
    _scheduler = None


def add_schedule_job(
    schedule_id: str, hour: int, minute: int, group_ids: list[int], focus: str
) -> None:
    """Add a scheduled brief generation job."""
    scheduler = _get_scheduler()
    job_id = f"schedule_{schedule_id}"

    # Remove existing job if any
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        generate_scheduled_brief,
        "cron",
        id=job_id,
        hour=hour,
        minute=minute,
        args=[schedule_id, group_ids, focus],
    )
    logger.info(f"Added schedule job {job_id} at {hour:02d}:{minute:02d}")


def remove_schedule_job(schedule_id: str) -> None:
    """Remove a scheduled brief generation job."""
    scheduler = _get_scheduler()
    job_id = f"schedule_{schedule_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        logger.info(f"Removed schedule job {job_id}")


def _load_schedules() -> List[Schedule]:
    """Load all schedules from database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, time, focus, group_ids, enabled
                FROM schedules
                ORDER BY time
            """)
            rows = cur.fetchall()
            return [Schedule.from_db_row(row) for row in rows]


def _save_schedule(schedule: Schedule) -> None:
    """Insert or update a schedule in database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO schedules (id, time, focus, group_ids, enabled)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    time = EXCLUDED.time,
                    focus = EXCLUDED.focus,
                    group_ids = EXCLUDED.group_ids,
                    enabled = EXCLUDED.enabled,
                    updated_at = CURRENT_TIMESTAMP
            """, (
                schedule.id,
                schedule.time,
                schedule.focus,
                schedule.group_ids,
                schedule.enabled,
            ))
    logger.info(f"Saved schedule {schedule.id} to database")


def _delete_schedule_from_db(schedule_id: str) -> bool:
    """Delete a schedule from database. Returns True if deleted."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schedules WHERE id = %s", (schedule_id,))
            return cur.rowcount > 0


def get_all_schedules() -> List[Schedule]:
    """Get all schedules."""
    return _load_schedules()


def get_schedule(schedule_id: str) -> Optional[Schedule]:
    """Get a schedule by ID."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, time, focus, group_ids, enabled
                FROM schedules
                WHERE id = %s
            """, (schedule_id,))
            row = cur.fetchone()
            if row:
                return Schedule.from_db_row(row)
            return None


def create_schedule(time_str: str, focus: str, group_ids: List[int]) -> Schedule:
    """Create a new schedule."""
    if not group_ids:
        raise ValueError("group_ids cannot be empty")

    # Generate ID
    schedule_id = str(uuid.uuid4())[:8]

    # Parse time - handle both string and time object
    if isinstance(time_str, str):
        hour, minute = map(int, time_str.split(":"))
        schedule_time = time(hour, minute)
    elif isinstance(time_str, time):  # type: ignore
        schedule_time = time_str
        hour = schedule_time.hour
        minute = schedule_time.minute
    else:
        raise ValueError(f"Invalid time format: {time_str}")

    schedule = Schedule(
        id=schedule_id,
        time=schedule_time,
        focus=focus,
        group_ids=group_ids,
        enabled=True,
    )

    _save_schedule(schedule)

    # Add to scheduler
    add_schedule_job(schedule_id, hour, minute, group_ids, focus)

    logger.info(f"Created schedule {schedule_id} at {time_str}")
    return schedule


def update_schedule(
    schedule_id: str,
    time_str: Optional[str] = None,
    focus: Optional[str] = None,
    group_ids: Optional[List[int]] = None,
    enabled: Optional[bool] = None,
) -> Optional[Schedule]:
    """Update an existing schedule."""
    if group_ids is not None and len(group_ids) == 0:
        raise ValueError("group_ids cannot be empty")

    schedule = get_schedule(schedule_id)
    if not schedule:
        return None

    if time_str is not None:
        # Parse time - handle both string and time object
        if isinstance(time_str, str):
            hour, minute = map(int, time_str.split(":"))
            schedule.time = time(hour, minute)
        elif isinstance(time_str, time):
            schedule.time = time_str
        else:
            raise ValueError(f"Invalid time format: {time_str}")
    if focus is not None:
        schedule.focus = focus
    if group_ids is not None:
        schedule.group_ids = group_ids
    if enabled is not None:
        schedule.enabled = enabled

    _save_schedule(schedule)

    # Update scheduler job
    remove_schedule_job(schedule_id)
    if schedule.enabled:
        add_schedule_job(
            schedule.id,
            schedule.time.hour,
            schedule.time.minute,
            schedule.group_ids,
            schedule.focus,
        )

    logger.info(f"Updated schedule {schedule_id}")
    return schedule


def delete_schedule(schedule_id: str) -> bool:
    """Delete a schedule."""
    if _delete_schedule_from_db(schedule_id):
        remove_schedule_job(schedule_id)
        logger.info(f"Deleted schedule {schedule_id}")
        return True
    return False


def update_schedule_jobs() -> None:
    """Update all schedule jobs based on current schedule configuration."""
    schedules = get_all_schedules()
    scheduler = _get_scheduler()

    # Remove all existing schedule jobs
    for job in scheduler.get_jobs():
        if job.id.startswith("schedule_"):
            scheduler.remove_job(job.id)

    # Add enabled schedules
    for schedule in schedules:
        if schedule.enabled:
            add_schedule_job(
                schedule.id,
                schedule.time.hour,
                schedule.time.minute,
                schedule.group_ids,
                schedule.focus,
            )

    logger.info(f"Updated {len([s for s in schedules if s.enabled])} schedule jobs")
