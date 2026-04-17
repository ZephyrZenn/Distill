import logging

logger = logging.getLogger(__name__)


async def generate_scheduled_brief(
    schedule_id: str,
    group_ids: list[int],
    focus: str,
    auto_expand: bool = False,
):
    """Generate a brief for specific groups with custom focus (async, single event loop).

    定时任务与手动任务共用一套 workflow 流程：
    - 先检查库存文章数量（24 小时内）
    - 不足则触发爬虫补充
    - 爬虫失败且仍无文章时放弃本次生成
    - 否则调用 workflow 生成简报
    - 若 auto_expand=True，自动展开所有可扩展主题

    Args:
        schedule_id: 调度任务ID
        group_ids: 分组ID列表
        focus: 用户关注点
        auto_expand: 是否自动展开所有可扩展主题
    """
    from apps.backend.services.task_service import (
        NoArticlesAvailableError,
        generate_brief_with_material_check,
    )

    logger.info(
        "Generating scheduled brief %s for groups %s with focus: %s (auto_expand=%s)",
        schedule_id,
        group_ids,
        focus,
        auto_expand,
    )

    try:
        _, brief_id, expandable_topics = await generate_brief_with_material_check(
            task_id=schedule_id,
            group_ids=group_ids,
            focus=focus,
        )
        logger.info("Finished generating scheduled brief %s (id=%d)", schedule_id, brief_id)

        if auto_expand and expandable_topics:
            from apps.backend.services.brief_service import expand_optional_topic

            for topic in expandable_topics:
                topic_id = topic.get("topic_id")
                if not topic_id:
                    continue
                try:
                    logger.info("Auto-expanding topic %s for brief %d", topic_id, brief_id)
                    await expand_optional_topic(brief_id, topic_id)
                    logger.info("Auto-expanded topic %s for brief %d", topic_id, brief_id)
                except Exception as e:
                    logger.error(
                        "Failed to auto-expand topic %s for brief %d: %s",
                        topic_id, brief_id, e, exc_info=True,
                    )

    except NoArticlesAvailableError as e:
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
