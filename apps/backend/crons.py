import asyncio
import logging
from functools import partial

logger = logging.getLogger(__name__)


async def generate_scheduled_brief(schedule_id: str, group_ids: list[int], focus: str):
    """Generate a brief for specific groups with custom focus (async, single event loop).

    Runs feed retrieval in a thread to avoid blocking the main event loop,
    then awaits the async brief generator.
    """
    from apps.backend.services.brief_service import generate_brief_for_groups_async
    from apps.backend.services.feed_service import retrieve_new_feeds

    logger.info(
        "Generating scheduled brief %s for groups %s with focus: %s",
        schedule_id,
        group_ids,
        focus,
    )
    try:
        # 拉取订阅源（异步，运行在当前事件循环）
        await retrieve_new_feeds(group_ids=group_ids)

        await generate_brief_for_groups_async(group_ids=group_ids, focus=focus)
        logger.info("Finished generating scheduled brief %s", schedule_id)
    except Exception as e:
        logger.exception("Error generating scheduled brief %s: %s", schedule_id, e)

def check_feed_health():
    """
    Check the health of the feed.
    """
    from apps.backend.services.feed_service import check_feed_health as _check_feed_health
    _check_feed_health()
