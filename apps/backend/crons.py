import logging

logger = logging.getLogger(__name__)


async def generate_scheduled_brief(
    schedule_id: str,
    group_ids: list[int],
    focus: str,
):
    """Generate a brief for specific groups with custom focus (async, single event loop).

    定时任务与手动任务共用一套 workflow 流程：
    - 先检查库存文章数量（24 小时内）
    - 不足则触发爬虫补充
    - 爬虫失败且仍无文章时放弃本次生成
    - 否则调用 workflow 生成简报

    Args:
        schedule_id: 调度任务ID
        group_ids: 分组ID列表
        focus: 用户关注点
    """
    from apps.backend.services.task_service import (
        NoArticlesAvailableError,
        generate_brief_with_material_check,
    )

    logger.info(
        "Generating scheduled brief %s for groups %s with focus: %s",
        schedule_id,
        group_ids,
        focus,
    )

    try:
        await generate_brief_with_material_check(
            task_id=schedule_id,
            group_ids=group_ids,
            focus=focus,
        )
        logger.info("Finished generating scheduled brief %s", schedule_id)
    except NoArticlesAvailableError as e:
        # 与手动任务保持一致：没有文章时不生成简报，但不中断调度器本身
        logger.warning(
            "Scheduled brief %s skipped due to no available articles: %s",
            schedule_id,
            e,
        )


def check_feed_health():
    """
    Check the health of the feed.
    """
    from apps.backend.services.feed_service import (
        check_feed_health as _check_feed_health,
    )

    _check_feed_health()
